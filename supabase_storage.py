"""
Supabase Storage integration for PDF hosting.
Upload PDFs to Supabase Storage and get public URLs.
"""

import os
from supabase import create_client, Client
import streamlit as st
from datetime import datetime, timedelta


class SupabaseStorage:
    """Handle PDF uploads to Supabase Storage"""
    
    def __init__(self, url: str, key: str, bucket_name: str = "pdfs"):
        """
        Initialize Supabase client.
        
        Args:
            url: Supabase project URL
            key: Supabase anon/service key
            bucket_name: Storage bucket name
        """
        self.client: Client = create_client(url, key)
        self.bucket_name = bucket_name
        self._ensure_bucket_exists()
    
    def _ensure_bucket_exists(self):
        """Create bucket if it doesn't exist"""
        try:
            # Try to get bucket
            self.client.storage.get_bucket(self.bucket_name)
        except:
            # Create bucket if doesn't exist
            try:
                self.client.storage.create_bucket(
                    self.bucket_name,
                    options={"public": True}  # Public access
                )
            except:
                pass  # Bucket might already exist
    
    def upload_pdf(self, file_path: str, folder: str = "uploads") -> str:
        """
        Upload PDF to Supabase Storage.
        
        Args:
            file_path: Local path to PDF
            folder: Folder in bucket (optional)
            
        Returns:
            Public URL to access the PDF
        """
        # Generate unique filename
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        original_name = os.path.basename(file_path)
        storage_path = f"{folder}/{timestamp}_{original_name}"
        
        # Read file
        with open(file_path, "rb") as f:
            file_data = f.read()
        
        # Upload to Supabase
        self.client.storage.from_(self.bucket_name).upload(
            path=storage_path,
            file=file_data,
            file_options={"content-type": "application/pdf"}
        )
        
        # Get public URL
        public_url = self.client.storage.from_(self.bucket_name).get_public_url(storage_path)
        
        return public_url
    
    def delete_pdf(self, storage_path: str):
        """Delete PDF from storage"""
        try:
            self.client.storage.from_(self.bucket_name).remove([storage_path])
        except:
            pass
    
    def list_pdfs(self, folder: str = "uploads"):
        """List all PDFs in folder"""
        try:
            files = self.client.storage.from_(self.bucket_name).list(folder)
            return files
        except:
            return []


def get_supabase_storage():
    """
    Get Supabase Storage instance from Streamlit secrets or env.
    
    Configure in .streamlit/secrets.toml:
    ```toml
    [supabase]
    url = "https://xxx.supabase.co"
    key = "your-anon-key"
    ```
    """
    try:
        # Try Streamlit secrets first (for cloud deployment)
        url = st.secrets["supabase"]["url"]
        key = st.secrets["supabase"]["key"]
    except:
        # Fallback to environment variables
        url = os.getenv("SUPABASE_URL")
        key = os.getenv("SUPABASE_KEY")
    
    if not url or not key:
        st.error("⚠️ Supabase credentials not configured!")
        st.info("""
        **Setup Supabase Storage:**
        
        1. Create project at https://supabase.com
        2. Go to Storage → Create bucket "pdfs" (public)
        3. Add to `.streamlit/secrets.toml`:
        ```toml
        [supabase]
        url = "https://xxx.supabase.co"
        key = "your-anon-key"
        ```
        """)
        return None
    
    return SupabaseStorage(url, key)


# Example usage
def upload_and_get_url(pdf_path: str) -> str:
    """
    Upload PDF to Supabase and return public URL.
    
    Args:
        pdf_path: Local path to PDF file
        
    Returns:
        Public URL or None if failed
    """
    storage = get_supabase_storage()
    if not storage:
        return None
    
    try:
        # Silent upload
        public_url = storage.upload_pdf(pdf_path)
        return public_url
    except Exception as e:
        st.error(f"Upload failed: {e}")
        return None
