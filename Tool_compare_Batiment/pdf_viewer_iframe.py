"""
PDF viewer using Mozilla PDF.js for Streamlit Cloud compatibility.
This approach works both locally and on Streamlit Cloud.
"""

import os
import base64
import streamlit as st
import streamlit.components.v1 as components
import fitz  # PyMuPDF
from PIL import Image
import io


def display_pdf_in_browser(pdf_path: str, height: int = 800):
    """
    Display PDF using Mozilla PDF.js viewer.
    Works on both local and Streamlit Cloud.
    
    Args:
        pdf_path: Path to PDF file
        height: Height in pixels
    """
    if not os.path.exists(pdf_path):
        st.error(f"PDF not found: {pdf_path}")
        return
    
    file_size_mb = os.path.getsize(pdf_path) / (1024 * 1024)
    st.caption(f"📊 File size: {file_size_mb:.1f}MB")
    
    # Read PDF as base64
    with open(pdf_path, "rb") as f:
        pdf_bytes = f.read()
    
    base64_pdf = base64.b64encode(pdf_bytes).decode('utf-8')
    
    # Use Mozilla PDF.js viewer (hosted on CDN)
    # This works on Streamlit Cloud!
    pdf_display = f'''
    <iframe
        src="https://mozilla.github.io/pdf.js/web/viewer.html?file=data:application/pdf;base64,{base64_pdf}"
        width="100%"
        height="{height}px"
        type="application/pdf"
        style="border: none;"
    ></iframe>
    '''
    
    # Render using components.html
    components.html(pdf_display, height=height + 10, scrolling=False)


# Backward compatibility aliases
display_pdf_iframe = display_pdf_in_browser
display_pdf_with_pdfjs = display_pdf_in_browser
