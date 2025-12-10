"""
Tool Compare - PDF Comparison Streamlit App
Supports 3 comparison modes with native PDF viewing and annotations.
"""

import os
import sys
import streamlit as st
import fitz  # PyMuPDF
from typing import Optional, Dict, List
import base64
import streamlit.components.v1 as components
import tempfile
import atexit

# Import comparison modules
from tool_compare_pages_2025 import compare_pages, PAGE_SIZE_TOLERANCE, IMAGE_SIZE_TOLERANCE
from tool_compare_lasolution_2026 import (
    extract_popup_annotations,
    get_text_around_annotation,
    check_annotation_with_gpt,
    get_openai_client,
    GPT_MODEL,
    compare_pages_lasolution
)
from tool_compare_assemblage import (
    extract_page_words_with_boxes,
    compare_pages_assemblage,
)

# Import helpers
from streamlit_helpers import (
    get_pdf_download_link,
    setup_openai_client_with_ui,
    display_mode2_results_summary,
    display_mode2_results_table,
    create_temp_dir_for_session,
    cleanup_temp_files,
    get_pdf_page_count,
    save_uploaded_file,
    extract_annotations_from_pdf,
    display_annotation_details,
    merge_nearby_annotations,
)

# Import iframe PDF viewer
from pdf_viewer_iframe import display_pdf_iframe, display_pdf_with_pdfjs

# Page config
st.set_page_config(
    page_title="Tool Compare - PDF Comparison",
    page_icon="📄",
    layout="wide",
    initial_sidebar_state="expanded"
)

# Custom CSS
st.markdown("""
<style>
    .main-header {
        font-size: 2.5rem;
        font-weight: bold;
        color: #1f77b4;
        text-align: center;
        margin-bottom: 1rem;
    }
    .mode-badge {
        display: inline-block;
        padding: 0.25rem 0.75rem;
        border-radius: 0.25rem;
        font-weight: 600;
        font-size: 0.875rem;
    }
    .mode-1 { background-color: #e3f2fd; color: #1565c0; }
    .mode-2 { background-color: #f3e5f5; color: #6a1b9a; }
    .mode-3 { background-color: #fff3e0; color: #e65100; }
</style>
""", unsafe_allow_html=True)

# Cleanup temp files on session end
if 'cleanup_registered' not in st.session_state:
    atexit.register(cleanup_temp_files)
    st.session_state.cleanup_registered = True


def merge_nearby_rects(rects_with_content: List[Dict], threshold: float = 20.0) -> List[Dict]:
    """
    Merge nearby rectangles with their content.
    
    Args:
        rects_with_content: List of {"rect": fitz.Rect, "content": str, "color": tuple}
        threshold: Distance threshold for merging
    
    Returns:
        List of merged rectangles with combined content
    """
    if not rects_with_content:
        return []
    
    # Sort by position (top to bottom, left to right)
    sorted_items = sorted(rects_with_content, key=lambda x: (x["rect"].y0, x["rect"].x0))
    merged = []
    current_group = [sorted_items[0]]
    
    for i in range(1, len(sorted_items)):
        current = sorted_items[i]
        last = current_group[-1]
        
        curr_rect = current["rect"]
        last_rect = last["rect"]
        
        # Check if rects are close enough to merge
        vertical_distance = abs(curr_rect.y0 - last_rect.y0)
        horizontal_distance = abs(curr_rect.x0 - last_rect.x1)
        
        # Merge if close vertically or horizontally adjacent
        should_merge = (
            (vertical_distance < threshold and horizontal_distance < threshold * 2) or
            (vertical_distance < threshold / 4 and horizontal_distance < threshold * 3)
        )
        
        if should_merge:
            current_group.append(current)
        else:
            # Merge current group
            if current_group:
                merged.append(_merge_group(current_group))
            current_group = [current]
    
    # Don't forget last group
    if current_group:
        merged.append(_merge_group(current_group))
    
    return merged


def _merge_group(group: List[Dict]) -> Dict:
    """Merge a group of annotations into one."""
    if len(group) == 1:
        return group[0]
    
    # Calculate bounding box
    min_x0 = min(item["rect"].x0 for item in group)
    min_y0 = min(item["rect"].y0 for item in group)
    max_x1 = max(item["rect"].x1 for item in group)
    max_y1 = max(item["rect"].y1 for item in group)
    
    # Combine content
    contents = [item["content"] for item in group]
    combined_content = " | ".join(contents)
    
    # Use color from first item (or most common)
    color = group[0].get("color", (1, 0, 0))
    title = group[0].get("title", "Merged")
    
    return {
        "rect": fitz.Rect(min_x0, min_y0, max_x1, max_y1),
        "content": combined_content,
        "color": color,
        "title": f"{title} (merged {len(group)})",
        "merged_count": len(group)
    }


def run_mode1_comparison(ref_path: str, final_path: str) -> tuple[str, int]:
	"""
	Mode 1: Compare product images using hash-based pairing.
	Returns (output_pdf_path, num_annotations)
	"""
	temp_dir = create_temp_dir_for_session()
	output_path = os.path.join(temp_dir, "mode1_result.pdf")
	
	try:
		# Import the new product comparison logic
		from tool_compare_pages_2025 import run
		
		# Run product extraction and comparison
		print("🔍 Mode 1: Extracting and comparing products...")
		run(ref_path, final_path, output_path)
		
		# Count annotations in output PDF
		doc = fitz.open(output_path)
		num_annotations = 0
		for page in doc:
			annots = list(page.annots())
			num_annotations += len(annots)
		doc.close()
		
		return output_path, num_annotations
		
	except Exception as e:
		st.error(f"Error in Mode 1 comparison: {e}")
		import traceback
		st.exception(e)
		return "", 0


def run_mode2_comparison(ref_path: str, final_path: str, client) -> tuple[str, List[Dict]]:
    """
    Run Mode 2: PAGES-LaSolution with GPT checking.
    
    Returns:
        (output_pdf_path, results_list)
    """
    temp_dir = create_temp_dir_for_session()
    output_path = os.path.join(temp_dir, "mode2_result.pdf")
    
    try:
        # Extract annotations
        all_annotations = extract_popup_annotations(ref_path)
        
        if not all_annotations:
            st.warning("No popup annotations found in reference PDF")
            return "", []
        
        # Group by page
        annotations_by_page = {}
        for ann in all_annotations:
            page_num = ann["page"]
            if page_num not in annotations_by_page:
                annotations_by_page[page_num] = []
            annotations_by_page[page_num].append(ann)
        
        # Open documents
        ref_doc = fitz.open(ref_path)
        final_doc = fitz.open(final_path)
        
        num_pages = min(ref_doc.page_count, final_doc.page_count)
        results = []
        
        # Progress bar
        progress_bar = st.progress(0)
        status_text = st.empty()
        
        for i in range(num_pages):
            if i not in annotations_by_page:
                continue
            
            ref_page = ref_doc.load_page(i)
            final_page = final_doc.load_page(i)
            annotations_on_page = annotations_by_page[i]
            
            status_text.text(f"Checking page {i + 1}/{num_pages} ({len(annotations_on_page)} annotations)...")
            
            for ann_data in annotations_on_page:
                annotation_content = ann_data["content"]
                rect = ann_data["rect"]
                
                # Get text around annotation
                current_text = get_text_around_annotation(final_page, rect, context_size=200)
                context_text = get_text_around_annotation(final_page, rect, context_size=400)
                
                # Check with GPT
                result = check_annotation_with_gpt(
                    client=client,
                    annotation_content=annotation_content,
                    current_text=current_text,
                    context_text=context_text,
                    model=GPT_MODEL
                )
                
                # Store result
                results.append({
                    "page": i + 1,
                    "status": result["status"],
                    "implemented": result["implemented"],
                    "reasoning": result.get("reasoning", ""),
                    "evidence": result.get("evidence", ""),
                    "annotation": annotation_content
                })
                
                # Add annotation to final PDF
                status = result["status"]
                if status == "implemented":
                    color = (0, 1, 0)  # green
                    title = "Mode2-LaSolution ✅"
                elif status == "not_implemented":
                    color = (1, 0, 0)  # red
                    title = "Mode2-LaSolution ❌"
                elif status == "partial":
                    color = (1, 1, 0)  # yellow
                    title = "Mode2-LaSolution ⚠️"
                else:
                    color = (0.5, 0.5, 0.5)  # gray
                    title = "Mode2-LaSolution ❓"
                
                try:
                    annot = final_page.add_rect_annot(rect)
                    annot.set_colors(stroke=color)
                    annot.set_border(width=2)
                    annot.set_info(
                        title=title,
                        content=f"Request: {annotation_content}\nStatus: {status}\nReason: {result['reasoning']}",
                        subject=status
                    )
                    annot.update()
                except:
                    pass
            
            # Update progress
            progress_bar.progress((i + 1) / num_pages)
        
        # Save result
        final_doc.save(output_path, garbage=4, deflate=True)
        ref_doc.close()
        final_doc.close()
        
        progress_bar.empty()
        status_text.empty()
        
        return output_path, results
    except Exception as e:
        st.error(f"Error in Mode 2 comparison: {e}")
        import traceback
        st.exception(e)
        return "", []


def run_mode3_comparison(ref_path: str, final_path: str) -> tuple[str, Dict]:
    """Mode 3: Compare 0ASSEMBLAGE_PDF vs final PDF - annotates BOTH PDFs"""
    try:
        # Use temp_dir for output paths
        temp_dir = create_temp_dir_for_session()
        output_ref = os.path.join(temp_dir, "mode3_ref_result.pdf")
        output_final = os.path.join(temp_dir, "mode3_final_result.pdf")
        
        results = {
            "total_pages": 0,
            "missing_texts": [],
            "extra_texts": []
        }
        
        # Open reference PDF for annotation
        ref_doc = fitz.open(ref_path)
        ref_pages = extract_page_words_with_boxes(ref_path)
        final_doc = fitz.open(final_path)
        
        num_pages = min(len(ref_pages), final_doc.page_count, ref_doc.page_count)
        results["total_pages"] = num_pages
        
        progress_bar = st.progress(0)
        
        # Annotate BOTH PDFs
        for i in range(num_pages):
            ref_page = ref_doc.load_page(i)
            ref_page_dict = ref_pages[i]
            final_page = final_doc.load_page(i)
            
            # This function now modifies both pages
            compare_pages_assemblage(ref_page, ref_page_dict, final_page, i)
            
            progress_bar.progress((i + 1) / num_pages)
        
        # Save BOTH annotated PDFs
        ref_doc.save(output_ref, garbage=4, deflate=True)
        ref_doc.close()
        
        final_doc.save(output_final, garbage=4, deflate=True)
        final_doc.close()
        
        progress_bar.empty()
        
        # Store BOTH paths in session state
        st.session_state['mode3_ref_pdf'] = output_ref
        st.session_state['mode3_final_pdf'] = output_final
        
        # Return final as primary result for backward compatibility
        return output_final, results
    except Exception as e:
        st.error(f"Error in Mode 3 comparison: {str(e)}")
        import traceback
        traceback.print_exc()
        return None, None


def main():
    st.markdown("<h1 class='main-header'>🔍 Tool Compare - PDF Comparison</h1>", unsafe_allow_html=True)
    
    # Sidebar
    st.sidebar.header("⚙️ Configuration")
    # Mode selection
    mode_options = {
        "PAGES_2025": "Mode 1: PAGES-2025 ⇄ PDF (final)",
        "PAGES_LASOLUTION": "Mode 2: PAGES-LaSolution-2026 ⇄ PDF (final)",
        "ASSEMBLAGE": "Mode 3: 0ASSEMBLAGE_PDF ⇄ PDF (final)"
    }
    
    # Sidebar Configuration
    with st.sidebar:
        st.markdown("---")
        st.subheader("⚙️ Configuration")
        
        # Mode selection
        mode_key = st.radio(
            "Comparison Mode",
            list(mode_options.keys()),
            format_func=lambda x: mode_options[x],
            key="selected_mode"
        )
        
        # Mode 2: API Key Configuration
        if mode_key == "PAGES_LASOLUTION":
            st.markdown("---")
            st.markdown("##### 🔑 OpenAI API Key (Required for Mode 2)")
            
            api_key_input = st.text_input(
                "Enter your OpenAI API Key",
                type="password",
                placeholder="sk-...",
                help="Required for GPT verification in Mode 2",
                key="mode2_api_key_sidebar"
            )
            
            if api_key_input:
                os.environ["OPENAI_API_KEY"] = api_key_input
                st.success("✓ API key configured")
            else:
                st.warning("⚠️ API key required")
    # Mode description
    if mode_key == "PAGES_2025":
        st.sidebar.info("🔵 **Mode 1**: Compare page sizes and main image dimensions between PAGES-2025 catalog and final PDF.")
    elif mode_key == "PAGES_LASOLUTION":
        st.sidebar.info("🟣 **Mode 2**: Use GPT AI to verify if popup annotation corrections have been implemented in final PDF.")
    else:
        st.sidebar.info("🟠 **Mode 3**: Word-by-word comparison to catch missing or extra text between assemblage PDF and final PDF.")
    
    st.sidebar.markdown("---")
    
    # File upload
    st.sidebar.subheader("📁 Upload PDF Files")
    
    uploaded_left = st.sidebar.file_uploader(
        "Reference PDF (Left)",
        type=['pdf'],
        key="upload_left",
        help="Upload the reference/source PDF"
    )
    
    uploaded_right = st.sidebar.file_uploader(
        "Final PDF (Right)",
        type=['pdf'],
        key="upload_right",
        help="Upload the final/target PDF to check"
    )
    
    # Save uploaded files
    left_path = None
    right_path = None
    
    if uploaded_left:
        left_path = save_uploaded_file(uploaded_left, "reference.pdf")
        st.sidebar.success(f"✅ {uploaded_left.name}")
    
    if uploaded_right:
        right_path = save_uploaded_file(uploaded_right, "final.pdf")
        st.sidebar.success(f"✅ {uploaded_right.name}")
    
    # Main content
    if not left_path or not right_path:
        st.info("👈 Please upload both PDF files to begin comparison")
        
        # Show examples
        st.markdown("### 📚 How to use")
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.markdown("""
            <div class='mode-badge mode-1'>MODE 1</div>
            
            **PAGES-2025 Comparison**
            - Checks page dimensions
            - Validates main image sizes
            - Highlights differences
            """, unsafe_allow_html=True)
        
        with col2:
            st.markdown("""
            <div class='mode-badge mode-2'>MODE 2</div>
            
            **GPT-Powered Verification**
            - Reads popup annotations
            - AI checks implementation
            - Detailed status reports
            """, unsafe_allow_html=True)
        
        with col3:
            st.markdown("""
            <div class='mode-badge mode-3'>MODE 3</div>
            
            **Text-Level Comparison**
            - Word-by-word diff
            - Catches missing text
            - Highlights extra text
            """, unsafe_allow_html=True)
        
        return
    
    # ===== PDFs UPLOADED - SHOW PREVIEW IMMEDIATELY =====
    st.markdown("---")
    st.markdown("### 📄 PDF Preview")
    st.info("👁️ PDFs loaded! View them below. Click 'Compare PDFs' button to analyze differences.")
    
    # Show PDFs side by side
    col1, col2 = st.columns(2)
    
    with col1:
        st.markdown("**📄 Reference PDF**")
        st.caption(f"📁 {os.path.basename(left_path)}")
        
        # Display with HTTP server iframe
        from pdf_viewer_iframe import display_pdf_in_browser
        display_pdf_in_browser(left_path, height=700)
    
    with col2:
        st.markdown("**📄 Final PDF**")
        st.caption(f"📁 {os.path.basename(right_path)}")
        
        # Display with HTTP server iframe
        display_pdf_in_browser(right_path, height=700)
    
    st.markdown("---")
    
    # Mode-specific setup
    if mode_key == "PAGES_LASOLUTION":
        # Mode 2 needs OpenAI client
        st.markdown("### 🤖 Mode 2: GPT AI Verification")
        st.markdown("Use GPT AI to verify if popup annotation corrections have been implemented in final PDF.")
        st.markdown("---")
        
        # Get client from API key in sidebar
        from tool_compare_lasolution_2026 import get_openai_client
        try:
            client = get_openai_client()
            if client:
                st.success("✓ API key configured - ready to verify annotations")
                
                # Preview annotations
                try:
                    annotations = extract_popup_annotations(left_path)
                    st.info(f"📝 Found **{len(annotations)}** annotations in reference PDF to verify")
                except Exception as e:
                    st.warning(f"Could not preview annotations: {e}")
            else:
                st.error("❌ Cannot proceed without API key. Please configure in sidebar.")
                return
        except Exception as e:
            st.error(f"❌ API key error: {e}")
            return
    
    st.markdown("### 🎯 Start Comparison")
    
    col1, col2 = st.columns([3, 1])
    
    with col1:
        if st.button("🔍 Compare PDFs", type="primary", use_container_width=True):
            with st.spinner(f"Running {mode_options[mode_key]}..."):
                
                if mode_key == "PAGES_2025":
                    # Mode 1
                    output_path, num_issues = run_mode1_comparison(left_path, right_path)
                    
                    if output_path:
                        st.session_state.result_pdf = output_path
                        st.session_state.comparison_done = True
                        
                        if num_issues > 0:
                            st.warning(f"⚠️ Found **{num_issues}** issues (page/image size differences)")
                        else:
                            st.success("✅ No issues found! PDFs match perfectly.")
                        
                        st.rerun()
                
                elif mode_key == "PAGES_LASOLUTION":
                    # Mode 2
                    client = setup_openai_client_with_ui() # Re-initialize client with potentially new API key
                    output_path, results = run_mode2_comparison(left_path, right_path, client)
                    
                    if output_path:
                        st.session_state.result_pdf = output_path
                        st.session_state.mode2_results = results
                        st.session_state.comparison_done = True
                        
                        st.success(f"✅ Checked **{len(results)}** annotations!")
                        st.rerun()
                
                else:
                    # Mode 3
                    output_path, results = run_mode3_comparison(left_path, right_path)
                    
                    if output_path:
                        st.session_state.result_pdf = output_path
                        st.session_state.mode3_results = results
                        st.session_state.comparison_done = True
                        
                        missing = len(results['missing_texts'])
                        extra = len(results['extra_texts'])
                        
                        if missing > 0 or extra > 0:
                            st.warning(f"⚠️ Found **{missing}** missing texts and **{extra}** extra texts")
                        else:
                            st.success("✅ Perfect match! No text differences found.")
                        
                        st.rerun()
    
    with col2:
        if st.button("🔄 Reset", use_container_width=True):
            # Clear session state
            for key in ['result_pdf', 'comparison_done', 'mode2_results', 'mode3_results']:
                if key in st.session_state:
                    del st.session_state[key]
            st.rerun()
    
    # Display results if comparison is done
    if st.session_state.get('comparison_done', False):
        st.markdown("---")
        st.markdown("### 📊 Results")
        
        # Mode-specific results display
        if mode_key == "PAGES_LASOLUTION" and 'mode2_results' in st.session_state:
            display_mode2_results_summary(st.session_state.mode2_results)
            st.markdown("---")
            display_mode2_results_table(st.session_state.mode2_results)
        
        elif mode_key == "ASSEMBLAGE" and 'mode3_results' in st.session_state:
            results = st.session_state.mode3_results
            
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Pages", results['total_pages'])
            with col2:
                st.metric("🟠 Missing Texts", len(results['missing_texts']))
            with col3:
                st.metric("🔵 Extra Texts", len(results['extra_texts']))
            
            # Details in expanders
            if results['missing_texts']:
                with st.expander(f"🟠 Missing Texts ({len(results['missing_texts'])})"):
                    for item in results['missing_texts'][:50]:  # Limit display
                        st.text(f"Page {item['page']}: {item['text']}")
            
            if results['extra_texts']:
                with st.expander(f"🔵 Extra Texts ({len(results['extra_texts'])})"):
                    for item in results['extra_texts'][:50]:
                        st.text(f"Page {item['page']}: {item['text']}")
        
        st.markdown("---")
        
        # Result PDF Download
        st.markdown("### 💾 Download Result")
        
        result_path = st.session_state.get('result_pdf', right_path)
        
        col1, col2, col3 = st.columns(3)
        
        with col1:
            st.metric("📄 Pages Compared", get_pdf_page_count(result_path))
        
        with col2:
            # Download reference
            with open(left_path, "rb") as f:
                st.download_button(
                    "📥 Download Reference",
                    data=f,
                    file_name="reference.pdf",
                    mime="application/pdf",
                    use_container_width=True
                )
        
        with col3:
            # Download result with annotations
            with open(result_path, "rb") as f:
                st.download_button(
                    "💾 Download Result (Annotated)",
                    data=f,
                    file_name=f"result_{mode_key.lower()}.pdf",
                    mime="application/pdf",
                    type="primary",
                    use_container_width=True
                )
        
        st.success("✅ Comparison complete! View results below or download PDFs.")
        
        # PDF Viewers - Show BOTH PDFs for Mode 3
        st.markdown("---")
        
        if mode_key == "ASSEMBLAGE" and 'mode3_ref_pdf' in st.session_state and 'mode3_final_pdf' in st.session_state:
            st.markdown("### 📄 Mode 3: Both PDFs with Highlights")
            st.caption("🔴 Red = Deleted/Changed | 🟢 Green = Added/Changed | 🔵 Blue = Moved")
            
            col_left, col_right = st.columns(2)
            
            with col_left:
                st.markdown("**📄 Reference PDF (with RED/BLUE highlights)**")
                ref_pdf_path = st.session_state['mode3_ref_pdf']
                st.caption(f"📁 {os.path.basename(left_path)}")
                
                from pdf_viewer_iframe import display_pdf_in_browser
                display_pdf_in_browser(ref_pdf_path, height=700)
                
                # Download button
                with open(ref_pdf_path, "rb") as f:
                    st.download_button(
                        "📥 Download Reference",
                        data=f,
                        file_name="mode3_reference_annotated.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key="download_mode3_ref"
                    )
            
            with col_right:
                st.markdown("**✅ Final PDF (with GREEN/BLUE highlights)**")
                final_pdf_path = st.session_state['mode3_final_pdf']
                st.caption(f"📁 {os.path.basename(right_path)}")
                
                # Display annotated PDF
                display_pdf_in_browser(final_pdf_path, height=700)
                
                # Download button
                with open(final_pdf_path, "rb") as f:
                    st.download_button(
                        "💾 Download Final (Annotated)",
                        data=f,
                        file_name="mode3_final_annotated.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                        key="download_mode3_final"
                    )
        else:
            # For Mode 1 and Mode 2, show single result
            st.markdown("### 📄 Result PDFs with Annotations")
            
            col_left, col_right = st.columns(2)
            
            with col_left:
                st.markdown("**📄 Reference PDF**")
                st.caption(f"📁 {os.path.basename(left_path)}")
                
                from pdf_viewer_iframe import display_pdf_in_browser
                display_pdf_in_browser(left_path, height=700)
                
                # Download button
                with open(left_path, "rb") as f:
                    st.download_button(
                        "📥 Download Reference",
                        data=f,
                        file_name="reference.pdf",
                        mime="application/pdf",
                        use_container_width=True,
                        key="download_ref_result"
                    )
            
            with col_right:
                st.markdown("**✅ Result PDF (with Annotations)**")
                result_path = st.session_state.get('result_pdf', right_path)
                st.caption(f"📁 {os.path.basename(result_path)}")
                
                # Display annotated PDF
                display_pdf_in_browser(result_path, height=700)
                
                # Download button
                with open(result_path, "rb") as f:
                    st.download_button(
                        "💾 Download Result (Annotated)",
                        data=f,
                        file_name=f"result_{mode_key.lower()}.pdf",
                        mime="application/pdf",
                        type="primary",
                        use_container_width=True,
                        key="download_result"
                    )
        
        # Annotation Details Viewer
        st.markdown("---")
        st.markdown("### 🔍 Annotation Details")
        
        # Extract annotations from result PDF
        result_path = st.session_state.get('result_pdf', right_path)
        
        with st.spinner("Loading annotations..."):
            annotations = extract_annotations_from_pdf(result_path)
        
        if annotations:
            # Show summary
            col1, col2, col3 = st.columns(3)
            with col1:
                st.metric("Total Annotations", len(annotations))
            with col2:
                pages_with_annots = len(set(a["page"] for a in annotations))
                st.metric("Pages with Annotations", pages_with_annots)
            with col3:
                # Merge option
                merge_enabled = st.checkbox("Merge nearby annotations", value=True, 
                                          help="Group annotations that are close together")
            
            # Merge if enabled
            if merge_enabled:
                annotations = merge_nearby_annotations(annotations, threshold=30.0)
                st.info(f"ℹ️ Merged into {len(annotations)} annotation groups")
            
            # Display annotations
            display_annotation_details(annotations)
        else:
            st.info("📝 No annotations found in result PDF")


if __name__ == "__main__":
    main()
