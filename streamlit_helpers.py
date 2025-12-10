"""
Helper functions for Streamlit PDF comparison app.
Provides utilities for PDF viewing, OpenAI client setup, and UI components.
"""

import os
import tempfile
import shutil
import uuid
import base64
import streamlit as st
from typing import Optional, Dict, List
import fitz  # PyMuPDF

try:
    from streamlit_pdf_viewer import pdf_viewer
    PDF_VIEWER_AVAILABLE = True
except ImportError:
    PDF_VIEWER_AVAILABLE = False
    print("Warning: streamlit-pdf-viewer not installed. Run: pip install streamlit-pdf-viewer")

from tool_compare_lasolution_2026 import get_openai_client


def display_pdf_with_viewer(pdf_path: str, width: int = 700, height: int = 800, 
                             annotations: Optional[List[Dict]] = None) -> None:
    """
    Display PDF using streamlit-pdf-viewer component.
    
    Args:
        pdf_path: Path to PDF file
        width: Width of viewer in pixels
        height: Height of viewer in pixels
        annotations: Optional list of annotations to overlay
    """
    if not PDF_VIEWER_AVAILABLE:
        st.error("PDF viewer component not installed. Install with: pip install streamlit-pdf-viewer")
        st.info("Fallback: Download the PDF to view it.")
        return
    
    if not os.path.exists(pdf_path):
        st.error(f"File not found: {pdf_path}")
        return
    
    try:
        # Read PDF as binary
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        
        # Display with viewer
        if annotations:
            pdf_viewer(input=pdf_bytes, width=width, height=height, annotations=annotations)
        else:
            pdf_viewer(input=pdf_bytes, width=width, height=height)
    except Exception as e:
        st.error(f"Error displaying PDF: {e}")
        st.info("Try downloading the PDF to view it.")


def get_pdf_download_link(pdf_path: str, label: str = "Download PDF") -> bytes:
    """
    Get PDF file bytes for download.
    
    Args:
        pdf_path: Path to PDF file
        label: Button label
        
    Returns:
        PDF bytes
    """
    if not os.path.exists(pdf_path):
        return b""
    
    try:
        with open(pdf_path, "rb") as f:
            return f.read()
    except Exception as e:
        st.error(f"Error reading PDF: {e}")
        return b""


def setup_openai_client_with_ui() -> Optional[object]:
    """
    Setup OpenAI client with UI for API key configuration.
    Checks environment variable first, then offers manual input.
    
    Returns:
        OpenAI client if successful, None otherwise
    """
    # Try to get client from environment variable
    client = get_openai_client()
    
    if client is not None:
        st.success("✅ OpenAI API key loaded from environment")
        return client
    
    # If no env var, show UI for manual input
    st.warning("⚠️ OpenAI API key not found in environment")
    
    with st.expander("🔑 Configure OpenAI API Key", expanded=True):
        st.info("""
        **Option 1 (Recommended):** Set in `.env` file:
        ```
        OPENAI_API_KEY=your-key-here
        GPT_MODEL=gpt-4o-mini
        ```
        
        **Option 2:** Enter manually below (not persisted):
        """)
        
        api_key = st.text_input(
            "Enter OpenAI API Key:",
            type="password",
            help="Your key will not be saved. Use .env file for permanent setup."
        )
        
        if api_key:
            try:
                from openai import OpenAI
                client = OpenAI(api_key=api_key)
                st.success("✅ API key configured!")
                return client
            except Exception as e:
                st.error(f"❌ Error: {e}")
                return None
    
    return None


def display_mode2_results_summary(results: List[Dict]) -> None:
    """
    Display summary statistics for Mode 2 results.
    
    Args:
        results: List of annotation check results
    """
    if not results:
        st.info("No results to display")
        return
    
    # Count by status
    implemented = sum(1 for r in results if r.get("status") == "implemented")
    not_implemented = sum(1 for r in results if r.get("status") == "not_implemented")
    partial = sum(1 for r in results if r.get("status") == "partial")
    unclear = sum(1 for r in results if r.get("status") == "unclear")
    
    # Display metrics in columns
    col1, col2, col3, col4, col5 = st.columns(5)
    
    with col1:
        st.metric("Total", len(results))
    with col2:
        st.metric("✅ Implemented", implemented)
    with col3:
        st.metric("❌ Not Implemented", not_implemented)
    with col4:
        st.metric("⚠️ Partial", partial)
    with col5:
        st.metric("❓ Unclear", unclear)


def display_mode2_results_table(results: List[Dict]) -> None:
    """
    Display detailed results table for Mode 2.
    
    Args:
        results: List of annotation check results
    """
    if not results:
        return
    
    st.markdown("### 📊 Detailed Results")
    
    for idx, result in enumerate(results):
        status = result.get("status", "unclear")
        page = result.get("page", "?")
        annotation = result.get("annotation", "")
        reasoning = result.get("reasoning", "")
        evidence = result.get("evidence", "")
        implemented = result.get("implemented", False)
        
        # Color and icon based on status
        if status == "implemented":
            color = "green"
            icon = "✅"
        elif status == "not_implemented":
            color = "red"
            icon = "❌"
        elif status == "partial":
            color = "orange"
            icon = "⚠️"
        else:
            color = "gray"
            icon = "❓"
        
        with st.expander(f"{icon} Annotation {idx + 1} - Page {page} - {status.upper()}", 
                         expanded=(status != "implemented")):
            st.markdown(f"**Status:** :{color}[{icon} {status.upper()}]")
            st.markdown(f"**Page:** {page}")
            st.markdown(f"**Implemented:** {'✅ Yes' if implemented else '❌ No'}")
            
            st.markdown("**Annotation Content:**")
            st.text_area(f"annotation_{idx}", value=annotation, height=60, 
                        disabled=True, label_visibility="collapsed")
            
            if reasoning:
                st.markdown("**Reasoning:**")
                st.info(reasoning)
            
            if evidence:
                st.markdown("**Evidence:**")
                st.success(evidence)


def create_temp_dir_for_session() -> str:
    """
    Create a temporary directory for the current session.
    
    Returns:
        Path to temp directory
    """
    if 'temp_dir' not in st.session_state:
        session_id = str(uuid.uuid4())[:8]
        temp_dir = tempfile.mkdtemp(prefix=f"pdf_compare_{session_id}_")
        st.session_state.temp_dir = temp_dir
    
    return st.session_state.temp_dir


def cleanup_temp_files() -> None:
    """Clean up temporary files from session."""
    if 'temp_dir' in st.session_state:
        try:
            shutil.rmtree(st.session_state.temp_dir, ignore_errors=True)
            del st.session_state.temp_dir
        except Exception as e:
            print(f"Error cleaning up temp files: {e}")


def get_pdf_page_count(pdf_path: str) -> int:
    """Get number of pages in PDF."""
    try:
        if not os.path.exists(pdf_path):
            return 0
        doc = fitz.open(pdf_path)
        count = doc.page_count
        doc.close()
        return count
    except:
        return 0


def extract_annotations_from_pdf(pdf_path: str) -> List[Dict]:
    """
    Extract all annotations from PDF.
    
    Returns:
        List of {"page": int, "title": str, "content": str, "rect": tuple}
    """
    annotations = []
    
    try:
        doc = fitz.open(pdf_path)
        
        for page_num in range(doc.page_count):
            page = doc.load_page(page_num)
            
            for annot in page.annots():
                try:
                    info = annot.info
                    title = info.get("title", "Annotation")
                    content = info.get("content", "")
                    rect = annot.rect
                    
                    if content:  # Only include annotations with content
                        annotations.append({
                            "page": page_num + 1,
                            "title": title,
                            "content": content,
                            "rect": (rect.x0, rect.y0, rect.x1, rect.y1),
                            "type": annot.type[1] if annot.type else "Unknown"
                        })
                except:
                    continue
        
        doc.close()
    except Exception as e:
        st.error(f"Error extracting annotations: {e}")
    
    return annotations


def display_annotation_details(annotations: List[Dict]):
    """
    Display annotation details in an interactive table.
    
    Args:
        annotations: List of annotation dictionaries
    """
    if not annotations:
        st.info("📝 No annotations found in PDF")
        return
    
    st.markdown(f"### 📌 Annotations ({len(annotations)} total)")
    
    # Group by page
    by_page = {}
    for ann in annotations:
        page = ann["page"]
        if page not in by_page:
            by_page[page] = []
        by_page[page].append(ann)
    
    # Display by page
    for page in sorted(by_page.keys()):
        page_annots = by_page[page]
        
        with st.expander(f"📄 Page {page} ({len(page_annots)} annotations)", expanded=(page == 1)):
            for idx, ann in enumerate(page_annots):
                col1, col2 = st.columns([1, 3])
                
                with col1:
                    # Determine icon based on title
                    title = ann.get("title", "")
                    if "✅" in title or "implemented" in title.lower():
                        icon = "✅"
                        color = "green"
                    elif "❌" in title or "not" in title.lower():
                        icon = "❌"
                        color = "red"
                    elif "⚠️" in title or "partial" in title.lower():
                        icon = "⚠️"
                        color = "orange"
                    elif "Mode1" in title:
                        icon = "🔵"
                        color = "blue"
                    elif "Mode3" in title:
                        icon = "🟠"
                        color = "orange"
                    else:
                        icon = "📌"
                        color = "gray"
                    
                    st.markdown(f"**{icon} {title}**")
                
                with col2:
                    content = ann.get("content", "No content")
                    # Format content for better readability
                    if len(content) > 200:
                        content = content[:200] + "..."
                    st.markdown(f":{color}[{content}]")
                
                if idx < len(page_annots) - 1:
                    st.markdown("---")


def merge_nearby_annotations(annotations: List[Dict], threshold: float = 30.0) -> List[Dict]:
    """
    Merge nearby annotations on the same page.
    
    Args:
        annotations: List of annotation dicts with 'rect' key
        threshold: Distance threshold in points
    
    Returns:
        List of merged annotations
    """
    if not annotations:
        return []
    
    # Group by page first
    by_page = {}
    for ann in annotations:
        page = ann.get("page", 1)
        if page not in by_page:
            by_page[page] = []
        by_page[page].append(ann)
    
    merged_all = []
    
    # Merge within each page
    for page, page_anns in by_page.items():
        # Sort by position
        sorted_anns = sorted(page_anns, key=lambda a: (a["rect"][1], a["rect"][0]))  # y0, x0
        
        merged_page = []
        current_group = [sorted_anns[0]]
        
        for i in range(1, len(sorted_anns)):
            current = sorted_anns[i]
            last = current_group[-1]
            
            # Calculate distance
            curr_rect = current["rect"]
            last_rect = last["rect"]
            
            v_dist = abs(curr_rect[1] - last_rect[1])  # y0 difference
            h_dist = abs(curr_rect[0] - last_rect[2])  # x0 to x1 difference
            
            # Merge if close
            if v_dist < threshold and h_dist < threshold * 2:
                current_group.append(current)
            else:
                # Finish current group
                merged_page.append(_merge_annotation_group(current_group))
                current_group = [current]
        
        # Don't forget last group
        if current_group:
            merged_page.append(_merge_annotation_group(current_group))
        
        merged_all.extend(merged_page)
    
    return merged_all


def _merge_annotation_group(group: List[Dict]) -> Dict:
    """Merge a group of annotations."""
    if len(group) == 1:
        return group[0]
    
    # Combine contents
    titles = list(set(g.get("title", "") for g in group))
    contents = [g.get("content", "") for g in group]
    
    # Calculate bounding rect
    x0s = [g["rect"][0] for g in group]
    y0s = [g["rect"][1] for g in group]
    x1s = [g["rect"][2] for g in group]
    y1s = [g["rect"][3] for g in group]
    
    return {
        "page": group[0]["page"],
        "title": f"{titles[0]} (×{len(group)})",
        "content": " | ".join(contents),
        "rect": (min(x0s), min(y0s), max(x1s), max(y1s)),
        "type": group[0].get("type", "Merged"),
        "merged_count": len(group)
    }


def save_uploaded_file(uploaded_file, filename: str) -> str:
    """
    Save uploaded file to temp directory.
    
    Args:
        uploaded_file: Streamlit UploadedFile object
        filename: Desired filename
        
    Returns:
        Path to saved file
    """
    temp_dir = create_temp_dir_for_session()
    file_path = os.path.join(temp_dir, filename)
    
    with open(file_path, "wb") as f:
        f.write(uploaded_file.getbuffer())
    
    return file_path
