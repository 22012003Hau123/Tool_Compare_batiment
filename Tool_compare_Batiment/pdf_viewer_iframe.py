"""
PDF viewer using HTTP server for reliable iframe display.
Based on proven solution from app.py.
"""

import os
import base64
import streamlit as st
import streamlit.components.v1 as components
import fitz  # PyMuPDF
from PIL import Image
import io
import http.server
import socketserver
import threading
import time
import socket
import shutil
from datetime import datetime

# Configuration
OUTPUT_PDF_DIR = "temp_pdfs_serve"
MAX_FILE_SIZE_MB = 2  # Files larger than this use HTTP server
HTTP_SERVER_PORT = 8765

# Create output directory
os.makedirs(OUTPUT_PDF_DIR, exist_ok=True)


def is_port_available(port):
    """Check if a port is available."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
        try:
            s.bind(('', port))
            return True
        except OSError:
            return False


class PDFHandler(http.server.SimpleHTTPRequestHandler):
    """HTTP handler with CORS headers for iframe embedding."""
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=OUTPUT_PDF_DIR, **kwargs)
    
    def end_headers(self):
        # Add CORS headers
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET')
        self.send_header('Access-Control-Allow-Headers', '*')
        super().end_headers()
    
    def log_message(self, format, *args):
        # Suppress HTTP server logs
        pass


def start_http_server(port=HTTP_SERVER_PORT):
    """
    Start HTTP server in separate thread if not already running.
    Returns True if server is ready, False if failed.
    """
    # Check if already running
    if 'http_server_running' in st.session_state and st.session_state.http_server_running:
        return True
    
    # Find available port
    max_attempts = 10
    for attempt in range(max_attempts):
        if not is_port_available(port):
            port += 1
            continue
        
        try:
            handler = PDFHandler
            httpd = socketserver.TCPServer(("", port), handler)
            httpd.allow_reuse_address = True
            
            # Start in daemon thread
            server_thread = threading.Thread(target=httpd.serve_forever, daemon=True)
            server_thread.start()
            
            st.session_state['http_server'] = httpd
            st.session_state['http_server_running'] = True
            st.session_state['http_server_port'] = port
            
            time.sleep(0.3)  # Give server time to start
            return True
            
        except OSError:
            port += 1
            if attempt == max_attempts - 1:
                return False
    
    return False


def save_pdf_to_serve_dir(pdf_path):
    """Save PDF to server directory and return filename."""
    filename = os.path.basename(pdf_path)
    if not filename.endswith('.pdf'):
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"pdf_{timestamp}.pdf"
    
    output_path = os.path.join(OUTPUT_PDF_DIR, filename)
    shutil.copy2(pdf_path, output_path)
    return filename


def display_pdf_in_browser(pdf_path: str, height: int = 800):
    """
    Display PDF in iframe using HTTP server (for large files) or base64 (for small files).
    
    Args:
        pdf_path: Path to PDF file
        height: Height in pixels
    """
    if not os.path.exists(pdf_path):
        st.error(f"PDF not found: {pdf_path}")
        return
    
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    
    if file_size_mb > MAX_FILE_SIZE_MB:
        # Large file - use HTTP server
        st.caption(f"📊 File size: {file_size_mb:.1f}MB (using HTTP server)")
        
        # Save to server directory
        filename = save_pdf_to_serve_dir(pdf_path)
        
        # Start server
        if start_http_server():
            port = st.session_state.get('http_server_port', HTTP_SERVER_PORT)
            pdf_url = f"http://localhost:{port}/{filename}"
            
            # Create iframe
            iframe_html = f'''
            <iframe
                src="{pdf_url}"
                width="100%"
                height="{height}px"
                type="application/pdf"
                style="border: 2px solid #444; border-radius: 8px;"
            ></iframe>
            '''
            
            st.markdown(iframe_html, unsafe_allow_html=True)
        else:
            st.error("Cannot start HTTP server. Download to view.")
            with open(pdf_path, "rb") as f:
                st.download_button(
                    "📥 Download PDF",
                    data=f,
                    file_name=filename,
                    mime="application/pdf"
                )
    else:
        # Small file - use base64 
        st.caption(f"📊 File size: {file_size_mb:.1f}MB (using base64)")
        
        with open(pdf_path, "rb") as f:
            pdf_bytes = f.read()
        
        base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
        
        # Create iframe with base64
        iframe_html = f'''
        <iframe
            src="data:application/pdf;base64,{base64_pdf}"
            width="100%"
            height="{height}px"
            type="application/pdf"
            style="border: 2px solid #444; border-radius: 8px;"
        ></iframe>
        '''
        
        st.markdown(iframe_html, unsafe_allow_html=True)


# Alternative using page rendering for maximum compatibility
def display_pdf_as_images(pdf_path: str, max_pages: int = 10):
    """
    Fallback: Display PDF as images with page selector.
    Use this if iframe doesn't work in user's browser.
    """
    try:
        doc = fitz.open(pdf_path)
        total_pages = doc.page_count
        doc.close()
        
        # Page selector
        col1, col2 = st.columns([3, 1])
        with col1:
            page_num = st.slider(
                "Page",
                min_value=1,
                max_value=total_pages,
                value=1,
                key=f"page_{pdf_path}"
            )
        with col2:
            st.metric("Total", total_pages)
        
        # Render selected page
        doc = fitz.open(pdf_path)
        page = doc.load_page(page_num - 1)
        mat = fitz.Matrix(2.0, 2.0)  # 2x zoom
        pix = page.get_pixmap(matrix=mat)
        img_data = pix.tobytes("png")
        img = Image.open(io.BytesIO(img_data))
        doc.close()
        
        st.image(img, use_container_width=True)
        
    except Exception as e:
        st.error(f"Error: {e}")
        with open(pdf_path, "rb") as f:
            st.download_button(
                "📥 Download",
                data=f,
                file_name=os.path.basename(pdf_path),
                mime="application/pdf"
            )


# Alises for compatibility
display_pdf_iframe = display_pdf_in_browser
display_pdf_with_pdfjs = display_pdf_in_browser
