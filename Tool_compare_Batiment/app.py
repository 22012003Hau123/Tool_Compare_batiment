"""
Streamlit Web App for PDF Comparison using OpenAI

Usage:
    streamlit run app.py

Requirements:
    pip install streamlit openai pymupdf pillow python-dotenv
"""

import streamlit as st
import os
import tempfile
import shutil
from pathlib import Path
import sys
import fitz  # PyMuPDF
from PIL import Image
import io
import base64
import http.server
import socketserver
import threading
import time
import socket
from datetime import datetime

# Import functions from compare.py
from compare_mode3 import (
    pdf_to_images,
    get_differences_from_openai,
    find_words_in_pdf,
    apply_highlights_to_pdf,
    MAX_HIGHLIGHTS_PER_WORD,
    HIGHLIGHT_COLOR_ADDED,
    HIGHLIGHT_COLOR_MOVED
)

# Page config
st.set_page_config(
    page_title="PDF Diff Viewer - AI Comparison",
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
    .sub-header {
        font-size: 1.2rem;
        color: #666;
        text-align: center;
        margin-bottom: 2rem;
    }
    .stProgress > div > div > div > div {
        background-color: #1f77b4;
    }
    .info-box {
        padding: 1rem;
        border-radius: 0.5rem;
        background-color: #f0f2f6;
        margin: 1rem 0;
    }
    </style>
""", unsafe_allow_html=True)

# Configuration
OUTPUT_PDFS_DIR = "output_pdfs"
MAX_FILE_SIZE_MB = 2  # Files larger than this will be served via HTTP
HTTP_SERVER_PORT = 8765

# Create output directory if it doesn't exist
os.makedirs(OUTPUT_PDFS_DIR, exist_ok=True)

def is_port_available(port):
    """Check if a port is available."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('', port))
            return True
        except OSError:
            return False

# HTTP Server management
class PDFHandler(http.server.SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=OUTPUT_PDFS_DIR, **kwargs)
    
    def end_headers(self):
        # Add CORS headers to allow iframe embedding
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()

def start_http_server(port=HTTP_SERVER_PORT):
    """Start HTTP server in a separate thread."""
    # Shutdown existing server if running
    if 'http_server' in st.session_state and st.session_state.get('http_server_running', False):
        try:
            httpd = st.session_state['http_server']
            # Check if server is still running
            if hasattr(httpd, 'socket') and httpd.socket:
                httpd.shutdown()
                httpd.server_close()
        except (OSError, AttributeError) as e:
            pass  # Ignore errors when shutting down (server might already be closed)
        finally:
            st.session_state['http_server_running'] = False
    
    # Try to find an available port
    max_attempts = 10
    original_port = port
    for attempt in range(max_attempts):
        # Check if port is available before trying to bind
        if not is_port_available(port):
            if attempt < max_attempts - 1:
                port += 1
                continue
            else:
                st.warning(f"Không thể khởi động HTTP server: Không tìm thấy port trống trong khoảng {original_port}-{port}")
                return False
            
        try:
            handler = PDFHandler
            httpd = socketserver.TCPServer(("", port), handler)
            httpd.allow_reuse_address = True
            
            # Start server in daemon thread
            server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            server_thread.start()
            
            st.session_state['http_server'] = httpd
            st.session_state['http_server_running'] = True
            st.session_state['http_server_port'] = port
            
            # Give server a moment to start
            time.sleep(0.5)
            return True
        except OSError as e:
            # Port is in use, try next port
            port += 1
            if attempt == max_attempts - 1:
                st.warning(f"Không thể khởi động HTTP server sau {max_attempts} lần thử. Port {original_port}-{port} đều đang được sử dụng.")
                return False
    return False

def save_pdf_to_output(pdf_path, filename=None):
    """Save PDF to output directory and return the filename."""
    if filename is None:
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"pdf_{timestamp}.pdf"
    
    output_path = os.path.join(OUTPUT_PDFS_DIR, filename)
    shutil.copy2(pdf_path, output_path)
    return filename

def display_pdf_in_iframe(pdf_path, height=800):
    """
    Display PDF in iframe. For files > 2MB, use HTTP server instead of base64.
    
    Args:
        pdf_path: Path to PDF file
        height: Height of iframe in pixels
    """
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    
    if file_size_mb > MAX_FILE_SIZE_MB:
        # File too large, use HTTP server
        # Save to output directory
        filename = os.path.basename(pdf_path)
        if not filename.endswith('.pdf'):
            filename = f"{filename}.pdf"
        
        saved_filename = save_pdf_to_output(pdf_path, filename)
        
        # Start HTTP server if not running
        if start_http_server():
            port = st.session_state.get('http_server_port', HTTP_SERVER_PORT)
            # Use localhost URL
            pdf_url = f"http://localhost:{port}/{saved_filename}"
            
            # Create iframe with URL
            pdf_display = f'<iframe src="{pdf_url}" width="100%" height="{height}px" type="application/pdf" style="border: 1px solid #ddd; border-radius: 5px;"></iframe>'
            
            st.markdown(pdf_display, unsafe_allow_html=True)
        else:
            st.error("Không thể khởi động HTTP server. Vui lòng tải file về để xem.")
    else:
        # File small enough, use base64
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        
        # Encode PDF to base64
        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        
        # Create iframe HTML
        pdf_display = f'<iframe src="data:application/pdf;base64,{base64_pdf}" width="100%" height="{height}px" type="application/pdf" style="border: 1px solid #ddd; border-radius: 5px;"></iframe>'
        
        # Display using st.markdown
        st.markdown(pdf_display, unsafe_allow_html=True)

def compare_pdfs_bidirectional(pdf_a_path, pdf_b_path, temp_dir):
    """
    Compare PDFs in both directions:
    - A→B: Highlight differences in PDF B (compared to A)
    - B→A: Highlight differences in PDF A (compared to B)
    
    Returns:
        Tuple of (result_b_path, result_a_path, stats_b, stats_a)
    """
    # Convert PDFs to images
    images_a = pdf_to_images(pdf_a_path)
    images_b = pdf_to_images(pdf_b_path)
    
    # Compare A→B (highlight B)
    changed_dict_ab, missing_list_ab, moved_list_ab = get_differences_from_openai(images_a, images_b)
    
    # Compare B→A (highlight A) - swap the images
    changed_dict_ba, missing_list_ba, moved_list_ba = get_differences_from_openai(images_b, images_a)
    
    # Filter results for A→B
    generic_words = {'de', 'ml', 'gr', 'pot', 'cartouche', 'la', 'le', 'les', 'et', 'en', 'à', 'du', 'des', 'un', 'une'}
    
    filtered_changed_ab = {k: v for k, v in changed_dict_ab.items() 
                           if len(k) >= 3 and k.lower() not in generic_words}
    words_to_highlight_ab = list(filtered_changed_ab.keys())
    missing_words_ab = [w for w in missing_list_ab if len(w) >= 3 and w.lower() not in generic_words]
    
    # Remove contradictions: if a word was replaced (in changed_dict), it shouldn't be in missing
    old_words_that_were_replaced_ab = {v.lower() for v in filtered_changed_ab.values() if v != "NEW"}
    missing_words_ab = [w for w in missing_words_ab if w.lower() not in old_words_that_were_replaced_ab]
    
    moved_words_ab = moved_list_ab
    
    # Filter results for B→A
    filtered_changed_ba = {k: v for k, v in changed_dict_ba.items() 
                           if len(k) >= 3 and k.lower() not in generic_words}
    words_to_highlight_ba = list(filtered_changed_ba.keys())
    missing_words_ba = [w for w in missing_list_ba if len(w) >= 3 and w.lower() not in generic_words]
    
    # Remove contradictions: if a word was replaced (in changed_dict), it shouldn't be in missing
    old_words_that_were_replaced_ba = {v.lower() for v in filtered_changed_ba.values() if v != "NEW"}
    missing_words_ba = [w for w in missing_words_ba if w.lower() not in old_words_that_were_replaced_ba]
    
    moved_words_ba = moved_list_ba
    
    # Find words and apply highlights for B (A→B comparison)
    highlights_added_b, rect_to_word_added_b = find_words_in_pdf(
        pdf_b_path, words_to_highlight_ab, MAX_HIGHLIGHTS_PER_WORD
    )
    highlights_moved_b, rect_to_word_moved_b = find_words_in_pdf(
        pdf_b_path, moved_words_ab, MAX_HIGHLIGHTS_PER_WORD
    )
    
    result_b_path = os.path.join(temp_dir, "result_b.pdf")
    apply_highlights_to_pdf(
        pdf_b_path,
        highlights_added_b,
        highlights_moved_b,
        result_b_path,
        missing_words_ab,
        filtered_changed_ab,
        rect_to_word_added_b,
        rect_to_word_moved_b
    )
    
    # Find words and apply highlights for A (B→A comparison)
    highlights_added_a, rect_to_word_added_a = find_words_in_pdf(
        pdf_a_path, words_to_highlight_ba, MAX_HIGHLIGHTS_PER_WORD
    )
    highlights_moved_a, rect_to_word_moved_a = find_words_in_pdf(
        pdf_a_path, moved_words_ba, MAX_HIGHLIGHTS_PER_WORD
    )
    
    result_a_path = os.path.join(temp_dir, "result_a.pdf")
    apply_highlights_to_pdf(
        pdf_a_path,
        highlights_added_a,
        highlights_moved_a,
        result_a_path,
        missing_words_ba,
        filtered_changed_ba,
        rect_to_word_added_a,
        rect_to_word_moved_a
    )
    
    # Stats
    stats_b = {
        'added': len(words_to_highlight_ab),
        'missing': len(missing_words_ab),
        'moved': len(moved_words_ab),
        'changed_dict': filtered_changed_ab
    }
    
    stats_a = {
        'added': len(words_to_highlight_ba),
        'missing': len(missing_words_ba),
        'moved': len(moved_words_ba),
        'changed_dict': filtered_changed_ba
    }
    
    return result_b_path, result_a_path, stats_b, stats_a

def main():
    # Header
    st.markdown('<p class="main-header">📄 PDF Diff Viewer</p>', unsafe_allow_html=True)
    st.markdown('<p class="sub-header">So sánh 2 file PDF bằng AI (OpenAI Vision)</p>', unsafe_allow_html=True)
    
    # Sidebar - Instructions
    with st.sidebar:
        st.header("📖 Hướng dẫn")
        st.markdown("""
        **Cách sử dụng:**
        1. Chọn file PDF A (gốc)
        2. Chọn file PDF B (đã chỉnh sửa)
        3. Nhấn nút "So sánh PDF (2 chiều)"
        4. Đợi AI phân tích (có thể mất vài phút)
        5. Xem kết quả hiển thị trực tiếp trên web
        
        **Cơ chế so sánh:**
        - **Bên trái (PDF B)**: Highlight những gì khác với PDF A
        - **Bên phải (PDF A)**: Highlight những gì khác với PDF B
        - So sánh 2 chiều để thấy rõ sự khác biệt
        
        **Màu sắc highlight:**
        - 🟢 **Xanh lá**: Nội dung thay đổi/thêm mới
        - 🔵 **Xanh dương**: Nội dung chỉ di chuyển vị trí
        - 🔴 **Icon đỏ**: Nội dung bị xóa (hover để xem)
        
        **Lưu ý:**
        - Cần có API key OpenAI trong file `.env`
        - File PDF lớn có thể mất nhiều thời gian
        - Chỉ hiển thị trang đầu tiên (có thể mở rộng sau)
        - File PDF > 2MB sẽ được lưu vào thư mục `output_pdfs/` và hiển thị qua HTTP server
        """)
        
        st.divider()
        
        # Show output directory info
        st.info(f"📁 **Thư mục lưu file lớn:**\n`{os.path.abspath(OUTPUT_PDFS_DIR)}`")
        
        st.divider()
        
        # Check API key
        from dotenv import load_dotenv
        load_dotenv()
        
        if os.environ.get("OPENAI_API_KEY"):
            st.success("✅ API Key đã được cấu hình")
        else:
            st.error("❌ Chưa có API Key")
            st.markdown("""
            Tạo file `.env` với nội dung:
            ```
            OPENAI_API_KEY=sk-your-key-here
            ```
            """)
    
    # Main content
    col1, col2 = st.columns(2)
    
    with col1:
        st.subheader("📄 PDF A (0ASSEMBLAGE_PDF) or (produfini_PDF) ")
        pdf_a_file = st.file_uploader(
            "Chọn file PDF gốc",
            type=['pdf'],
            key="pdf_a",
            help="File PDF ban đầu, chưa chỉnh sửa"
        )
        
        if pdf_a_file:
            st.info(f"✅ Đã chọn: **{pdf_a_file.name}**")
            st.caption(f"Kích thước: {pdf_a_file.size / 1024:.1f} KB")
    
    with col2:
        st.subheader("📝 PDF B (produfini_PDF) or (0ASSEMBLAGE_PDF) ")
        pdf_b_file = st.file_uploader(
            "Chọn file PDF đã chỉnh sửa",
            type=['pdf'],
            key="pdf_b",
            help="File PDF đã được chỉnh sửa, cần so sánh với PDF A"
        )
        
        if pdf_b_file:
            st.info(f"✅ Đã chọn: **{pdf_b_file.name}**")
            st.caption(f"Kích thước: {pdf_b_file.size / 1024:.1f} KB")
    
    # Compare button
    st.divider()
    
    if pdf_a_file and pdf_b_file:
        if st.button("🔍 So sánh PDF (2 chiều)", type="primary", use_container_width=True):
            # Check API key
            if not os.environ.get("OPENAI_API_KEY"):
                st.error("❌ Chưa cấu hình OpenAI API Key. Vui lòng tạo file `.env` với `OPENAI_API_KEY=sk-...`")
                st.stop()
            
            # Create temporary files
            temp_dir = tempfile.mkdtemp()
            pdf_a_path = os.path.join(temp_dir, "pdf_a.pdf")
            pdf_b_path = os.path.join(temp_dir, "pdf_b.pdf")
            
            # Save uploaded files
            with open(pdf_a_path, "wb") as f:
                f.write(pdf_a_file.getbuffer())
            
            with open(pdf_b_path, "wb") as f:
                f.write(pdf_b_file.getbuffer())
            
            # Progress tracking
            progress_bar = st.progress(0)
            status_text = st.empty()
            
            try:
                # Step 1: Convert PDFs to images
                status_text.text("📸 [1/5] Đang chuyển PDF thành ảnh...")
                progress_bar.progress(5)
                
                # Step 2: Compare both directions
                status_text.text("🤖 [2/5] Đang so sánh A→B (highlight PDF B)...")
                progress_bar.progress(20)
                
                status_text.text("🤖 [3/5] Đang so sánh B→A (highlight PDF A)...")
                progress_bar.progress(40)
                
                result_b_path, result_a_path, stats_b, stats_a = compare_pdfs_bidirectional(
                    pdf_a_path, pdf_b_path, temp_dir
                )
                
                progress_bar.progress(80)
                
                # Step 3: Prepare PDFs for display
                status_text.text("🖼️ [4/5] Đang chuẩn bị PDF để hiển thị...")
                progress_bar.progress(90)
                
                progress_bar.progress(100)
                status_text.text("✅ Hoàn thành!")
                
                # Display results
                st.success("🎉 So sánh hoàn tất!")
                
                # Show statistics
                col_stat1, col_stat2 = st.columns(2)
                
                with col_stat1:
                    st.markdown("### 📝 PDF B (Bên trái)")
                    st.markdown(f"""
                    - 🟢 **Thay đổi/Thêm mới**: {stats_b['added']}
                    - 🔴 **Bị xóa**: {stats_b['missing']}
                    - 🔵 **Di chuyển**: {stats_b['moved']}
                    """)
                
                with col_stat2:
                    st.markdown("### 📄 PDF A (Bên phải)")
                    st.markdown(f"""
                    - 🟢 **Thay đổi/Thêm mới**: {stats_a['added']}
                    - 🔴 **Bị xóa**: {stats_a['missing']}
                    - 🔵 **Di chuyển**: {stats_a['moved']}
                    """)
                
                st.divider()
                
                # Display PDFs side by side
                st.markdown("### 📄 Xem PDF đã highlight")
                
                col_left, col_right = st.columns(2)
                
                with col_left:
                    st.markdown("#### 📝 PDF B (Highlight so với A)")
                    # Display PDF in iframe
                    display_pdf_in_iframe(result_b_path, height=800)
                    
                    # Download button for PDF B
                    with open(result_b_path, "rb") as f:
                        pdf_b_data = f.read()
                    st.download_button(
                        label="📥 Tải PDF B",
                        data=pdf_b_data,
                        file_name=f"highlighted_B_{pdf_b_file.name}",
                        mime="application/pdf",
                        key="download_b"
                    )
                
                with col_right:
                    st.markdown("#### 📄 PDF A (Highlight so với B)")
                    # Display PDF in iframe
                    display_pdf_in_iframe(result_a_path, height=800)
                    
                    # Download button for PDF A
                    with open(result_a_path, "rb") as f:
                        pdf_a_data = f.read()
                    st.download_button(
                        label="📥 Tải PDF A",
                        data=pdf_a_data,
                        file_name=f"highlighted_A_{pdf_a_file.name}",
                        mime="application/pdf",
                        key="download_a"
                    )
                
                # Store paths in session state for later access
                st.session_state['result_b_path'] = result_b_path
                st.session_state['result_a_path'] = result_a_path
                st.session_state['temp_dir'] = temp_dir
                st.session_state['stats_b'] = stats_b
                st.session_state['stats_a'] = stats_a
                
            except Exception as e:
                st.error(f"❌ Lỗi: {str(e)}")
                st.exception(e)
                progress_bar.progress(0)
                status_text.text("")
    
    else:
        st.info("👆 Vui lòng chọn cả 2 file PDF để bắt đầu so sánh")
    

    # Footer
    st.divider()
    st.markdown("""
    <div style='text-align: center; color: #666; padding: 1rem;'>
        <p>Powered by OpenAI GPT-4o Vision | Made with ❤️ using Streamlit</p>
    </div>
    """, unsafe_allow_html=True)

if __name__ == "__main__":
    main()

