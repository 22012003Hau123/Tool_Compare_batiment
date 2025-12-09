"""
Compare 2 PDF files using OpenAI API and highlight differences in PDF B.

Usage:
    python compare.py <pdf_a_path> <pdf_b_path> <output_pdf_path>

Requirements:
    pip install openai pymupdf pillow python-dotenv

Set your OpenAI API key in .env file:
    OPENAI_API_KEY=sk-your-api-key-here
"""

import os
import sys
import json
import re
import subprocess
import tempfile
import base64
from collections import defaultdict
import fitz  # PyMuPDF
from openai import OpenAI
from dotenv import load_dotenv
from PIL import Image
import pytesseract

# Load environment variables from .env file
load_dotenv()

# Auto-detect Tesseract location
# Get Tesseract path from .env or use default paths
TESSERACT_CMD = os.getenv('TESSERACT_CMD')
if TESSERACT_CMD:
    pytesseract.pytesseract.tesseract_cmd = TESSERACT_CMD

# ============================================================================
# Configuration
# ============================================================================

OPENAI_MODEL = "gpt-4.1"  # hoặc "gpt-4-turbo" nếu cần
HIGHLIGHT_COLOR_ADDED = (0.0, 1.0, 0.0)  # Green - text (added/changed)
HIGHLIGHT_COLOR_MOVED = (0.0, 0.5, 1.0)  # Blue - move (repositioned)
HIGHLIGHT_OPACITY = 0.3
MAX_HIGHLIGHTS_PER_WORD = 3  # Giới hạn số lần tô mỗi từ
OCR_DPI = 300  # DPI for OCR (higher = better quality but slower)
OCR_LANG = 'fra'  # Tesseract language (fra=French, eng=English, vie=Vietnamese)

# Poppler path
POPPLER_PATH = os.path.join(os.path.dirname(__file__), "poppler-25.11.0", "Library", "bin")
PDFTOPPM_EXE = os.path.join(POPPLER_PATH, "pdftoppm.exe")

# ============================================================================
# Step 1: Convert PDFs to images
# ============================================================================

def pdf_to_images(pdf_path):
    """
    Convert all pages of a PDF to PNG images using Poppler.
    
    Args:
        pdf_path: Path to PDF file
        
    Returns:
        List of image file paths (one per page)
    """
    if not os.path.exists(PDFTOPPM_EXE):
        raise FileNotFoundError(f"pdftoppm.exe not found at: {PDFTOPPM_EXE}")
    
    doc = fitz.open(pdf_path)
    num_pages = doc.page_count
    doc.close()
    
    temp_dir = tempfile.gettempdir()
    output_prefix = os.path.join(temp_dir, f"pdf_compare_{os.urandom(4).hex()}")
    
    # Convert all pages at once
    cmd = [
        PDFTOPPM_EXE,
        "-png",
        "-r", str(OCR_DPI),  # Resolution
        pdf_path,
        output_prefix
    ]
    
    print(f"  Converting PDF to images (DPI={OCR_DPI})...")
    result = subprocess.run(cmd, capture_output=True, text=True)
    
    if result.returncode != 0:
        raise Exception(f"pdftoppm failed: {result.stderr}")
    
    # Collect all generated images
    image_paths = []
    for page_num in range(1, num_pages + 1):  # pdftoppm uses 1-indexed
        image_path = f"{output_prefix}-{page_num}.png"
        if os.path.exists(image_path):
            image_paths.append(image_path)
        else:
            print(f"  Warning: Image for page {page_num} not created")
    
    print(f"  ✅ Created {len(image_paths)} images")
    return image_paths

def encode_image_to_base64(image_path):
    """Encode image file to base64 string for OpenAI API."""
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode('utf-8')

# ============================================================================
# Step 2: Send to OpenAI and get differences
# ============================================================================

def get_differences_from_openai(images_a, images_b):
    """
    Send images from PDF A and PDF B to OpenAI Vision API.
    Ask it to return words that are different by comparing the visual content.
    
    Args:
        images_a: List of image file paths from PDF A
        images_b: List of image file paths from PDF B
        
    Returns:
        Tuple of (changed_dict, missing_list, moved_list)
        - changed_dict: Dict mapping new_word_in_B -> original_word_in_A
        - missing_list: List of words removed from A
        - moved_list: List of words that just moved position
    """
    client = OpenAI(api_key=os.environ.get("OPENAI_API_KEY"))
    
    # Encode images to base64 (only first page for now, can extend to multiple pages)
    image_a_base64 = encode_image_to_base64(images_a[0]) if images_a else ""
    image_b_base64 = encode_image_to_base64(images_b[0]) if images_b else ""
    
    prompt = """You are comparing two PDF documents (A and B). These are product catalogs.

I will show you TWO IMAGES:
- First image: PDF A (original)
- Second image: PDF B (modified)

Your task: Visually compare the images and identify ONLY MEANINGFUL CHANGES.

Return a mapping showing what changed from A to B:

1. **text** - Changed or NEW content (object format):
   - Key: New text in B
   - Value: Original text in A (or "NEW" if didn't exist in A)
   - Example: {{"Brun": "TES"}} means "Brun" in B replaced "TES" from A
   - Example: {{"Brun": "NEW"}} means "Brun" is completely NEW in B (didn't exist in A)
   - **IMPORTANT**: If text appears in B but NOT in A, put it in "text" with value "NEW", NOT in "missing"
   
2. **missing** - Deleted content (array format):
   - Content visible in A but NOT in B at all (completely removed)
   - **IMPORTANT**: Do NOT put text here if it appears in B (even if in different position)
   - Example: ["Product X", "Code 123"]
   
3. **move** - Significantly relocated content (array format):
   - Content moved to DIFFERENT SECTION/COLUMN
   - This should be RARE - only for major repositioning across sections
   - Example: ["Item moved to other column"]

**CRITICAL RULES TO IGNORE:**
❌ **DO NOT report as "move"**:
   - Line breaks (text wrapping to next line in same column)
   - Vertical spacing differences (text higher/lower by a few lines)
   - Row reordering within same table/section
   - Alignment changes (left-aligned → center-aligned)
   - Font size or style changes
   
❌ **DO NOT report generic/formatting words**:
   - "de", "ml", "Cartouche", "Pot", etc. (unless part of meaningful change)

✅ **ONLY report**:
   - NEW products/codes not in original → Put in "text" with value "NEW"
   - DELETED products/codes from original → Put in "missing" (only if completely absent from B)
   - CHANGED values (prices, quantities, specifications) → Put in "text" with old value
   - Items moved to COMPLETELY DIFFERENT locations (rare) → Put in "move"

**CRITICAL LOGIC - NO CONTRADICTIONS**:
- If text exists in B but NOT in A → "text": {{"TextInB": "NEW"}}
- If text exists in A but NOT in B → "missing": ["TextFromA"]
- If text changed from A to B → "text": {{"NewText": "OldText"}}
- **NEVER put text in "missing" if it appears anywhere in B**
- **NEVER put the SAME word in both "text" and "missing"** - if "OldWord" was replaced by "NewWord", put only {{"NewWord": "OldWord"}} in "text", NOT "OldWord" in "missing"
- **If "text" contains {{"NewWord": "OldWord"}}, then "OldWord" must NOT appear in "missing"** (it was replaced, not deleted)

**Expected result**: Most documents will have VERY FEW items in "text" and "missing", and "move" should be EMPTY or nearly empty unless content truly relocated across sections.

**RESPONSE FORMAT - STRICT:**

Return ONLY valid JSON (no markdown, no backticks, no extra text):

{{
  "text": {{"new_word_B": "old_word_A", "another_new_B": "another_old_A"}},
  "missing": ["deleted1", "deleted2"],
  "move": []
}}

**IMPORTANT:**
- "text" MUST be an OBJECT (dict), NOT a string
- Each key is the NEW text visible in B
- Each value is the ORIGINAL text from A that it replaced
- If something is completely new (not in A), use value "NEW"
- "missing" and "move" are ARRAYS (lists)

**Examples of CORRECT responses:**

Example 1 - Simple replacement:
{{
  "text": {{"Brun": "TES"}},
  "missing": [],
  "move": []
}}
→ Word "Brun" in B replaced "TES" from A
→ Note: "TES" is NOT in "missing" because it was replaced, not deleted

Example 1b - WRONG (contradictory):
❌ {{
  "text": {{"Brun": "TES"}},
  "missing": ["TES"],  // WRONG! TES was replaced, not deleted
  "move": []
}}

Example 2 - Multiple changes:
{{
  "text": {{"200ml": "100ml", "15.00": "10.00", "Product Z": "NEW"}},
  "missing": ["Product Y", "Old code"],
  "move": []
}}
→ "200ml" replaced "100ml", "15.00" replaced "10.00", "Product Z" is new
→ "Product Y" and "Old code" were completely removed (no replacement)

Example 2b - Replacement vs Deletion:
{{
  "text": {{"TES": "Brun"}},
  "missing": ["Product X"],
  "move": []
}}
→ "TES" in B replaced "Brun" from A (so "Brun" is NOT in "missing")
→ "Product X" was completely deleted from B (no replacement)

Example 3 - No changes:
{{
  "text": {{}},
  "missing": [],
  "move": []
}}

**WRONG formats (DO NOT USE):**
❌ {{"text": "Brun,TES", ...}} (string, not object)
❌ {{"text": ["Brun"], ...}} (array, not object)
❌ Missing the "text", "missing", or "move" keys
"""

    try:
        # Build messages with images
        messages = [
            {
                "role": "system",
                "content": "You are an intelligent document comparison assistant specialized in product catalogs. You can see and compare visual content. You understand context and ignore minor formatting differences. Return only valid JSON."
            },
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_a_base64}",
                            "detail": "high"
                        }
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": f"data:image/png;base64,{image_b_base64}",
                            "detail": "high"
                        }
                    }
                ]
            }
        ]
        
        response = client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=messages,
            temperature=0.1,  # Lower for more consistent JSON format
            max_tokens=800,   # Increased to allow more detailed response
            response_format={"type": "json_object"}  # Force JSON output
        )
        
        result = response.choices[0].message.content.strip()
        print("\n=== OpenAI Response ===")
        print(result)
        print("=======================\n")
        
        # Parse JSON
        try:
            data = json.loads(result)
            text_dict = data.get("text", {})
            missing_list = data.get("missing", [])
            move_list = data.get("move", [])
            
            # Ensure correct types
            if not isinstance(text_dict, dict):
                text_dict = {}
            if not isinstance(missing_list, list):
                missing_list = []
            if not isinstance(move_list, list):
                move_list = []
            
            return text_dict, missing_list, move_list
            
        except json.JSONDecodeError as e:
            print(f"Warning: Could not parse JSON: {e}")
            print(f"Raw response: {result}")
            return {}, [], []
    
    except Exception as e:
        print(f"Error calling OpenAI API: {e}")
        return {}, [], []

# ============================================================================
# Step 3: Find words in PDF B and get their coordinates
# ============================================================================

def find_words_in_pdf(pdf_path, words_to_find, max_instances_per_word=5):
    """
    Find instances of given words in a PDF and return their rectangles.
    Uses smart matching: tries full phrase first, then individual words if not found.
    
    Args:
        pdf_path: Path to PDF file
        words_to_find: List of words/phrases to search for
        max_instances_per_word: Maximum number of times to highlight each word
        
    Returns:
        Tuple of (highlights_by_page, rect_to_search_word)
        - highlights_by_page: Dict mapping page_num -> list of fitz.Rect objects
        - rect_to_search_word: Dict mapping rect -> original search word (for annotation)
    """
    if not words_to_find:
        return {}, {}
    
    doc = fitz.open(pdf_path)
    highlights_by_page = defaultdict(list)
    rect_to_search_word = {}  # Track which search word created which rect
    
    # Track how many times each word has been highlighted
    word_counts = defaultdict(int)
    
    # Build lookup - keep all as phrases, will split if needed
    phrases = []
    
    for w in words_to_find:
        w_clean = w.strip()
        if not w_clean:
            continue
        phrases.append(w_clean.lower())
    
    # Generic words to skip
    skip_words = {'de', 'ml', 'gr', 'pot', 'cartouche', 'la', 'le', 'les', 'et', 'en', 'à', 'du', 'des', 'un', 'une', 'blanc', 'gris', 'noir', 'beige', 'marron'}
    
    for page_num in range(doc.page_count):
        page = doc.load_page(page_num)
        
        for phrase in phrases:
            if word_counts[phrase] >= max_instances_per_word:
                continue
            
            # Try 1: Search for full phrase
            text_instances = page.search_for(phrase, flags=fitz.TEXT_DEHYPHENATE)
            
            if text_instances:
                # Found full phrase - use it
                for rect in text_instances[:max_instances_per_word - word_counts[phrase]]:
                    highlights_by_page[page_num].append(rect)
                    rect_to_search_word[id(rect)] = phrase  # Track which search word created this rect
                    word_counts[phrase] += 1
                    if word_counts[phrase] >= max_instances_per_word:
                        break
            else:
                # Try 2: Phrase not found, search for individual meaningful words
                words_in_phrase = [w.strip() for w in phrase.split() if len(w.strip()) > 2]
                words_data = page.get_text("words")
                
                for word in words_in_phrase:
                    if word.lower() in skip_words:
                        continue  # Skip generic words
                    
                    # Search this word
                    for word_info in words_data:
                        x0, y0, x1, y1, word_text = word_info[:5]
                        word_normalized = word_text.strip().lower()
                        
                        if word_normalized == word.lower():
                            # Check if already highlighted enough
                            word_key = f"{phrase}_{word}"
                            if word_counts[word_key] >= max_instances_per_word:
                                break
                            
                            rect = fitz.Rect(x0, y0, x1, y1)
                            highlights_by_page[page_num].append(rect)
                            rect_to_search_word[id(rect)] = phrase  # Track original phrase
                            word_counts[word_key] += 1
                            word_counts[phrase] += 1
                            
                            if word_counts[phrase] >= max_instances_per_word:
                                break
                    
                    if word_counts[phrase] >= max_instances_per_word:
                        break
    
    doc.close()
    
    # Print summary
    print("\n=== Highlight Summary ===")
    for word, count in sorted(word_counts.items(), key=lambda x: -x[1]):
        if count > 0:
            print(f"  '{word}': {count} instances")
    print("=========================\n")
    
    return highlights_by_page, rect_to_search_word

# ============================================================================
# Step 4: Apply highlights to PDF B
# ============================================================================

def apply_highlights_to_pdf(pdf_path, highlights_added, highlights_moved, output_path, missing_words_list=None, changed_mapping=None, rect_to_word_added=None, rect_to_word_moved=None):
    """
    Apply highlight annotations to PDF and save to output file.
    Also adds a text box showing missing words.
    
    Args:
        pdf_path: Path to input PDF
        highlights_added: Dict of page_num -> list of Rect objects (green - text)
        highlights_moved: Dict of page_num -> list of Rect objects (blue - move)
        output_path: Path to save highlighted PDF
        missing_words_list: List of words that were deleted (to display in text box)
        changed_mapping: Dict mapping new_word -> original_word for annotation text
        rect_to_word_added: Dict mapping rect id -> search word
        rect_to_word_moved: Dict mapping rect id -> search word
    """
    if changed_mapping is None:
        changed_mapping = {}
    if rect_to_word_added is None:
        rect_to_word_added = {}
    if rect_to_word_moved is None:
        rect_to_word_moved = {}
    doc = fitz.open(pdf_path)
    
    # Add missing words text box on first page (top-left corner)
    if missing_words_list and len(missing_words_list) > 0:
        page = doc.load_page(0)
        
        # Filter out very short/generic words
        filtered_missing = [w for w in missing_words_list if len(w) >= 3]
        
        if not filtered_missing:
            print("[Missing Words] All missing items too short/generic, skipping text box")
        else:
            # Create full text content for popup (no limit)
            missing_text = "DELETED/REMOVED from original:\n\n" + "\n".join([f"• {w}" for w in filtered_missing])
            
            # Position: top-left corner (just need a point for the icon)
            icon_position = fitz.Point(15, 15)
            
            # Add text annotation as small icon with popup
            try:
                # Create text annotation (displays as small icon)
                text_annot = page.add_text_annot(
                    icon_position,
                    missing_text,
                    icon="Comment"  # Icon types: "Comment", "Note", "Help", "Key", etc.
                )
                
                # Customize icon color
                text_annot.set_colors(stroke=(0.9, 0, 0))  # Red icon
                text_annot.set_opacity(1.0)
                text_annot.set_info(
                    title="AIComparer - Removed",
                    subject=f"{len(filtered_missing)} items deleted"
                )
                text_annot.update()
                
                print(f"\n[Missing Words Icon] ✅ Added icon on page 0 with {len(filtered_missing)} items in popup (filtered from {len(missing_words_list)})")
                print(f"  → Hover over red icon at top-left to see deleted items")
                
            except Exception as e:
                print(f"[Missing Words Icon] ⚠️  Error: {e}")
    
    # Helper function to merge and add highlights
    def add_highlights_for_type(highlights_dict, color, label, is_added_changed=False, rect_to_word=None):
        total_annotations = 0
        for page_num, rects in highlights_dict.items():
            if not rects:
                continue
                
            page = doc.load_page(page_num)
            
            # Merge adjacent rectangles on same line
            # Track which original rects contributed to each merged rect
            rects_sorted = sorted(rects, key=lambda r: (r.y0, r.x0))
            merged_rects = []
            merged_to_original = {}  # Map merged rect index -> list of original rects
            
            if rects_sorted:
                current_rect = rects_sorted[0]
                current_originals = [rects_sorted[0]]
                
                for next_rect in rects_sorted[1:]:
                    y_tolerance = 10
                    x_tolerance = 10
                    
                    if (abs(current_rect.y0 - next_rect.y0) < y_tolerance and
                        abs(current_rect.y1 - next_rect.y1) < y_tolerance and
                        next_rect.x0 <= current_rect.x1 + x_tolerance):
                        # Merge
                        current_rect = current_rect | next_rect
                        current_originals.append(next_rect)
                    else:
                        # Save current merged rect
                        merged_rects.append(current_rect)
                        merged_to_original[len(merged_rects)-1] = current_originals
                        # Start new
                        current_rect = next_rect
                        current_originals = [next_rect]
                
                # Add last one
                merged_rects.append(current_rect)
                merged_to_original[len(merged_rects)-1] = current_originals
            
            # Add highlight annotations with popup text
            for idx, rect in enumerate(merged_rects):
                try:
                    annot = page.add_highlight_annot(rect)
                    annot.set_colors(stroke=color)
                    annot.set_opacity(HIGHLIGHT_OPACITY)
                    
                    # Set annotation content (popup text showing original value)
                    if is_added_changed and changed_mapping and rect_to_word:
                        # Get original rects that were merged into this rect
                        original_rects = merged_to_original.get(idx, [])
                        
                        # Find the search word from original rects
                        search_word = None
                        for orig_rect in original_rects:
                            rect_id = id(orig_rect)
                            if rect_id in rect_to_word:
                                search_word = rect_to_word[rect_id]
                                break
                        
                        # Get original value from changed_mapping using search_word as key
                        if search_word:
                            # search_word is lowercase, need to find exact match in changed_mapping
                            original_value = None
                            new_word_display = None
                            
                            for new_word_key, old_word_val in changed_mapping.items():
                                if new_word_key.lower() == search_word:
                                    original_value = old_word_val
                                    new_word_display = new_word_key
                                    break
                            
                            if original_value:
                                if original_value == "NEW":
                                    annot.set_info(
                                        title="New Addition",
                                        subject="Not in original",
                                        content=f"NEW: {new_word_display}\n\n(Did not exist in PDF A)"
                                    )
                                else:
                                    annot.set_info(
                                        title="Changed",
                                        subject=f"Was: {original_value}",
                                        content=f"Original (A): {original_value}\n\nChanged to (B): {new_word_display}"
                                    )
                            else:
                                annot.set_info(title=f"{label}")
                        else:
                            annot.set_info(title=f"{label}")
                    else:
                        annot.set_info(title=f"AIComparer - {label}")
                    
                    annot.update()
                    total_annotations += 1
                except Exception as e:
                    print(f"Error adding {label} highlight on page {page_num}: {e}")
            
            print(f"Page {page_num}: Added {len(merged_rects)} {label} highlights (from {len(rects)} words)")
        return total_annotations
    
    # Add green highlights for added/changed content (with original values in popup)
    if highlights_added:
        print("\n[Highlighting Added/Changed]")
        add_highlights_for_type(highlights_added, HIGHLIGHT_COLOR_ADDED, "Added/Changed", is_added_changed=True, rect_to_word=rect_to_word_added)
    
    # Add blue highlights for moved content
    if highlights_moved:
        print("\n[Highlighting Moved]")
        add_highlights_for_type(highlights_moved, HIGHLIGHT_COLOR_MOVED, "Moved", is_added_changed=False, rect_to_word=rect_to_word_moved)
    
    # Save output
    doc.save(output_path)
    doc.close()
    print(f"\nHighlighted PDF saved to: {output_path}")

# ============================================================================
# Main workflow
# ============================================================================

def main():
    if len(sys.argv) != 4:
        print("Usage: python compare.py <pdf_a_path> <pdf_b_path> <output_pdf_path>")
        print("\nExample:")
        print('  python compare.py document_original.pdf document_edited.pdf output_highlighted.pdf')
        sys.exit(1)
    
    pdf_a_path = sys.argv[1]
    pdf_b_path = sys.argv[2]
    output_path = sys.argv[3]
    
    # Validate inputs
    if not os.path.exists(pdf_a_path):
        print(f"Error: PDF A not found: {pdf_a_path}")
        sys.exit(1)
    
    if not os.path.exists(pdf_b_path):
        print(f"Error: PDF B not found: {pdf_b_path}")
        sys.exit(1)
    
    if not os.environ.get("OPENAI_API_KEY"):
        print("Error: OPENAI_API_KEY not found.")
        print("\nTạo file .env trong thư mục này với nội dung:")
        print('  OPENAI_API_KEY=sk-your-api-key-here')
        print("\nHoặc copy từ file mẫu:")
        print('  copy env.example .env')
        print("\nLấy API key tại: https://platform.openai.com/api-keys")
        sys.exit(1)
    
    print("=" * 70)
    print("PDF Comparison using OpenAI")
    print("=" * 70)
    print(f"PDF A (original): {pdf_a_path}")
    print(f"PDF B (modified): {pdf_b_path}")
    print(f"Output file:      {output_path}")
    print("=" * 70)
    
    # Step 1: Convert PDFs to images for AI vision
    print("\n[1/4] Converting PDFs to images for AI vision analysis...")
    
    print(f"\n  Processing PDF A (original)...")
    images_a = pdf_to_images(pdf_a_path)
    
    print(f"\n  Processing PDF B (modified)...")
    images_b = pdf_to_images(pdf_b_path)
    
    print(f"\n  PDF A: {len(images_a)} pages as images")
    print(f"  PDF B: {len(images_b)} pages as images")
    
    try:
        # Step 2: Get differences from OpenAI Vision API
        print("\n[2/4] Sending images to OpenAI Vision API for comparison...")
        changed_dict, missing_list, moved_list = get_differences_from_openai(images_a, images_b)
        
        # Extract words to highlight and their original values
        # changed_dict = {"Brun": "TES", "200ml": "100ml", ...}
        words_to_highlight_with_original = changed_dict  # Keep full dict for annotation
        words_to_highlight = list(changed_dict.keys())  # Just keys for finding
        missing_words = missing_list
        moved_words = moved_list
        
        # Filter out overly generic/short words (post-processing safety check)
        generic_words = {'de', 'ml', 'gr', 'pot', 'cartouche', 'la', 'le', 'les', 'et', 'en', 'à', 'du', 'des', 'un', 'une'}
        
        # Filter words_to_highlight (keys of dict)
        filtered_changed_dict = {k: v for k, v in words_to_highlight_with_original.items() 
                                 if len(k) >= 3 and k.lower() not in generic_words}
        words_to_highlight_with_original = filtered_changed_dict
        words_to_highlight = list(filtered_changed_dict.keys())
        
        # Filter missing words
        missing_words = [w for w in missing_words if len(w) >= 3 and w.lower() not in generic_words]
        
        # Remove contradictions: if a word was replaced (in changed_dict), it shouldn't be in missing
        # changed_dict values are the OLD words that were replaced
        old_words_that_were_replaced = {v.lower() for v in filtered_changed_dict.values() if v != "NEW"}
        missing_words = [w for w in missing_words if w.lower() not in old_words_that_were_replaced]
        
        if old_words_that_were_replaced:
            print(f"[Post-filter] Removed {len([w for w in missing_list if w.lower() in old_words_that_were_replaced])} contradictory items from missing (they were replaced, not deleted)")
        
        print(f"[Post-filter] Kept {len(words_to_highlight)} added/changed items after filtering")
        
        # Log moved words (will be highlighted in blue)
        if moved_words:
            print(f"\n[INFO] Found {len(moved_words)} items that only moved position (will be highlighted in blue):")
            for i, word in enumerate(moved_words[:5], 1):
                print(f"    {i}. {word}")
            if len(moved_words) > 5:
                print(f"    ... and {len(moved_words) - 5} more")
        
        if not words_to_highlight and not missing_words:
            print("\n  No real content changes found (only position changes or formatting).")
            print("  Creating copy of PDF B without highlights...")
            import shutil
            shutil.copy(pdf_b_path, output_path)
            print(f"  Copied to: {output_path}")
            return
        
        print(f"\n  Found {len(words_to_highlight)} added/changed words/phrases:")
        for i, word in enumerate(words_to_highlight[:10], 1):
            print(f"    {i}. {word}")
        if len(words_to_highlight) > 10:
            print(f"    ... and {len(words_to_highlight) - 10} more")
        
        if missing_words:
            print(f"\n  Found {len(missing_words)} missing/deleted words:")
            for i, word in enumerate(missing_words[:10], 1):
                print(f"    {i}. {word}")
            if len(missing_words) > 10:
                print(f"    ... and {len(missing_words) - 10} more")
        
        # Step 3: Find words in PDF B
        print("\n[3/4] Finding word locations in PDF B...")
        
        # Find added/changed words (green) with original values
        highlights_added, rect_to_word_added = find_words_in_pdf(pdf_b_path, words_to_highlight, MAX_HIGHLIGHTS_PER_WORD)
        total_added = sum(len(rects) for rects in highlights_added.values())
        print(f"  Found {total_added} added/changed instances across {len(highlights_added)} pages")
        
        # Find moved words (blue)
        highlights_moved, rect_to_word_moved = find_words_in_pdf(pdf_b_path, moved_words, MAX_HIGHLIGHTS_PER_WORD)
        total_moved = sum(len(rects) for rects in highlights_moved.values())
        print(f"  Found {total_moved} moved instances across {len(highlights_moved)} pages")
        
        # Step 4: Apply highlights with annotation text showing original values
        print("\n[4/4] Applying highlights to PDF B...")
        apply_highlights_to_pdf(pdf_b_path, highlights_added, highlights_moved, output_path, missing_words, words_to_highlight_with_original, rect_to_word_added, rect_to_word_moved)
        
        print("\n" + "=" * 70)
        print("Done! Check the output file:")
        print(f"  {output_path}")
        print("\nSummary:")
        print(f"  🟢 Green highlights: {len(words_to_highlight)} added/changed items")
        if moved_words:
            print(f"  🔵 Blue highlights: {len(moved_words)} moved/repositioned items")
        if missing_words:
            print(f"  🔴 Red text box (top-left): {len(missing_words)} deleted items")
        print("=" * 70)
    
    finally:
        # Always cleanup temporary images
        print("\n[Cleanup] Removing temporary images...")
        for img_path in images_a + images_b:
            try:
                if os.path.exists(img_path):
                    os.remove(img_path)
            except Exception as e:
                print(f"  Warning: Could not delete {img_path}: {e}")

if __name__ == "__main__":
    main()

