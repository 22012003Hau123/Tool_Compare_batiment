import sys
import json
from typing import List, Dict, Optional
import fitz  # PyMuPDF

import os

try:
	from openai import OpenAI
except ImportError:
	print("Warning: openai package not found. Install with: pip install openai")
	OpenAI = None

try:
	from dotenv import load_dotenv
	load_dotenv()  # Load environment variables from .env file
except ImportError:
	print("Warning: python-dotenv not found. Install with: pip install python-dotenv")

# Load API key from environment variable for security
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
GPT_MODEL = os.getenv("GPT_MODEL", "gpt-4o-mini")


def get_openai_client() -> Optional[OpenAI]:
	"""
	Khởi tạo OpenAI client từ environment variable.
	
	Returns:
		OpenAI client nếu thành công, None nếu không có API key hoặc import error
	"""
	if OpenAI is None:
		print("Error: openai package not installed. Run: pip install openai")
		return None
	
	if not OPENAI_API_KEY or OPENAI_API_KEY == "your-api-key-here":
		print("Error: OPENAI_API_KEY not configured.")
		print("Please set OPENAI_API_KEY in .env file or environment variable.")
		print("See .env.example for template.")
		return None
	
	try:
		return OpenAI(api_key=OPENAI_API_KEY)
	except Exception as e:
		print(f"Error initializing OpenAI client: {e}")
		return None


def extract_popup_annotations(pdf_path: str) -> List[Dict]:
	"""
	Trích xuất tất cả popup annotations từ PDF.

	Trả về:
		list[dict]: [{
			"page": int,
			"annotation": fitz.Annot,
			"content": str,  # nội dung popup
			"rect": fitz.Rect,  # vị trí annotation
		}, ...]
	"""
	doc = fitz.open(pdf_path)
	annotations = []
	
	for page_num in range(doc.page_count):
		page = doc.load_page(page_num)
		annots = page.annots()
		
		for annot in annots:
			# Lấy popup annotations và text annotations
			annot_type = annot.type[0]
			if annot_type in [fitz.PDF_ANNOT_POPUP, fitz.PDF_ANNOT_TEXT, fitz.PDF_ANNOT_FREE_TEXT]:
				try:
					# Lấy nội dung annotation
					content = annot.info.get("content", "") or annot.info.get("title", "")
					
					# Nếu không có content, thử lấy từ popup liên kết
					if not content and hasattr(annot, "popup"):
						try:
							popup = annot.popup
							if popup:
								content = popup.info.get("content", "")
						except:
							pass
					
					if content and content.strip():
						rect = annot.rect
						annotations.append({
							"page": page_num,
							"annotation": annot,
							"content": content.strip(),
							"rect": rect,
						})
				except Exception as e:
					print(f"Warning: Error extracting annotation on page {page_num}: {e}")
					continue
	
	doc.close()
	return annotations


def get_text_around_annotation(page: fitz.Page, rect: fitz.Rect, context_size: int = 200) -> str:
	"""
	Lấy text xung quanh vị trí annotation với kích thước context nhất định.
	"""
	# Mở rộng vùng để lấy context
	expanded_rect = fitz.Rect(
		max(0, rect.x0 - context_size),
		max(0, rect.y0 - context_size),
		min(page.rect.width, rect.x1 + context_size),
		min(page.rect.height, rect.y1 + context_size)
	)
	return page.get_text("text", clip=expanded_rect).strip()


def check_annotation_with_gpt(
	client: OpenAI,
	annotation_content: str,
	current_text: str,
	context_text: str,
	model: str = GPT_MODEL
) -> Dict:
	"""
	Sử dụng GPT API để kiểm tra xem annotation đã được thực hiện chưa.
	
	Args:
		client: OpenAI client
		annotation_content: Nội dung của popup annotation (yêu cầu sửa đổi)
		current_text: Text hiện tại trong PDF tại vị trí annotation
		context_text: Text xung quanh để có context
		model: Model GPT để sử dụng
	
	Returns:
		dict: {
			"implemented": bool,
			"confidence": float,  # 0.0 - 1.0
			"reasoning": str,
			"status": str  # "implemented", "not_implemented", "partial", "unclear"
		}
	"""
	if client is None:
		return {
			"implemented": False,
			"confidence": 0.0,
			"reasoning": "OpenAI client not available",
			"evidence": "",
			"status": "unclear"
		}
	
	prompt = f"""Bạn là một chuyên gia kiểm tra tài liệu PDF. Nhiệm vụ của bạn là kiểm tra xem một yêu cầu sửa đổi từ popup annotation đã được thực hiện trong PDF chưa.

YÊU CẦU SỬA ĐỔI TỪ POPUP ANNOTATION:
{annotation_content}

TEXT HIỆN TẠI TRONG PDF (tại vị trí annotation):
{current_text}

CONTEXT XUNG QUANH (để hiểu rõ hơn):
{context_text}

Hãy phân tích và trả lời:
1. Yêu cầu sửa đổi đã được thực hiện chưa? (implemented: true/false)
2. Lý do (reasoning: giải thích ngắn gọn)
3. Đưa ra dẫn chứng cụ thể
4. Trạng thái: "implemented" (đã thực hiện), "not_implemented" (chưa thực hiện), "partial" (thực hiện một phần), "unclear" (không rõ ràng)

Trả lời theo định dạng JSON:
{{
	"implemented": true/false,
	"reasoning": "lý do",
	"evidence": "dẫn chứng cụ thể",
	"status": "implemented/not_implemented/partial/unclear"
}}"""
	
	try:
		response = client.chat.completions.create(
			model=model,
			messages=[
				{
					"role": "system",
					"content": "Bạn là một chuyên gia kiểm tra tài liệu. Trả lời chỉ bằng JSON, không có text thêm."
				},
				{
					"role": "user",
					"content": prompt
				}
			],
			temperature=0.3,
			response_format={"type": "json_object"}
		)
		
		result = json.loads(response.choices[0].message.content)
		
		return {
			"implemented": result.get("implemented", False),
			"confidence": float(result.get("confidence", 0.0)),
			"reasoning": result.get("reasoning", ""),
			"evidence": result.get("evidence", ""),  # Dẫn chứng cụ thể
			"status": result.get("status", "unclear")
		}
	except Exception as e:
		print(f"Error calling GPT API: {e}")
		return {
			"implemented": False,
			"confidence": 0.0,
			"reasoning": f"Error: {str(e)}",
			"evidence": "",
			"status": "unclear"
		}


def compare_pages_lasolution(
	ref_page: fitz.Page,
	final_page: fitz.Page,
	page_index: int,
	annotations_on_page: List[Dict],
	client: Optional[OpenAI]
):
	"""
	Mode 2 – PAGES-LaSolution-2026:
	Đọc popup annotations từ ref_page và kiểm tra xem đã được sửa trong final_page chưa.
	Sử dụng GPT API để kiểm tra và annotate kết quả lên final_page.

	- Đã thực hiện: khung xanh lá
	- Chưa thực hiện: khung đỏ
	- Thực hiện một phần: khung vàng
	- Không rõ ràng: khung xám
	"""
	if not annotations_on_page:
		return
	
	for ann_data in annotations_on_page:
		annotation_content = ann_data["content"]
		rect = ann_data["rect"]
		
		# Lấy text hiện tại tại vị trí annotation trong final_page
		current_text = get_text_around_annotation(final_page, rect, context_size=200)
		context_text = get_text_around_annotation(final_page, rect, context_size=400)
		
		# Kiểm tra với GPT
		result = check_annotation_with_gpt(
			client=client,
			annotation_content=annotation_content,
			current_text=current_text,
			context_text=context_text,
			model=GPT_MODEL
		)
		
		# Xác định màu và nội dung annotation dựa trên kết quả
		status = result["status"]
		if status == "implemented":
			color = (0, 1, 0)  # xanh lá
			title = "Mode2-LaSolution ✅"
			subject = "Đã thực hiện"
		elif status == "not_implemented":
			color = (1, 0, 0)  # đỏ
			title = "Mode2-LaSolution ❌"
			subject = "Chưa thực hiện"
		elif status == "partial":
			color = (1, 1, 0)  # vàng
			title = "Mode2-LaSolution ⚠️"
			subject = "Thực hiện một phần"
		else:  # unclear
			color = (0.5, 0.5, 0.5)  # xám
			title = "Mode2-LaSolution ❓"
			subject = "Không rõ ràng"
		
		# Tạo annotation trên final_page
		try:
			annot = final_page.add_rect_annot(rect)
			annot.set_colors(stroke=color)
			annot.set_border(width=0.5)
			
			content_msg = (
				f"Yêu cầu: {annotation_content}\n"
				f"Trạng thái: {status}\n"
				f"Confidence: {result['confidence']:.2f}\n"
				f"Lý do: {result['reasoning']}"
			)
			
			annot.set_info(
				title=title,
				content=content_msg,
				subject=subject,
			)
			annot.update()
		except Exception as e:
			print(f"Mode2: error adding annotation on page {page_index}: {e}")


def main(ref_path: str, final_path: str, output_path: str | None = None):
	"""
	Mode 2 – PAGES-LaSolution-2026:
	Đọc popup annotations từ ref_path và kiểm tra xem đã được sửa trong final_path chưa.
	
	Args:
		ref_path: Đường dẫn đến PDF có popup annotations
		final_path: Đường dẫn đến PDF cần kiểm tra
		output_path: Đường dẫn để lưu PDF đã annotate (optional)
	"""
	# Đọc popup annotations từ ref_path
	print(f"Mode 2 (LaSolution): Đang đọc popup annotations từ {ref_path}...")
	all_annotations = extract_popup_annotations(ref_path)
	
	if not all_annotations:
		print("Không tìm thấy popup annotations nào trong file reference.")
		return
	
	print(f"Tìm thấy {len(all_annotations)} popup annotation(s).")
	
	# Khởi tạo OpenAI client
	client = get_openai_client()
	if client is None:
		print("Warning: Không thể khởi tạo OpenAI client. Sẽ bỏ qua kiểm tra GPT.")
	
	# Mở các PDF
	ref_doc = fitz.open(ref_path)
	final_doc = fitz.open(final_path)

	# Nhóm annotations theo trang
	annotations_by_page: Dict[int, List[Dict]] = {}
	for ann in all_annotations:
		page_num = ann["page"]
		if page_num not in annotations_by_page:
			annotations_by_page[page_num] = []
		annotations_by_page[page_num].append(ann)
	
	num_pages = min(ref_doc.page_count, final_doc.page_count)
	print(f"Đang kiểm tra {num_pages} trang...")

	# Xử lý từng trang
	for i in range(num_pages):
		ref_page = ref_doc.load_page(i)
		final_page = final_doc.load_page(i)
		
		# Lấy annotations trên trang này
		annotations_on_page = annotations_by_page.get(i, [])
		
		if annotations_on_page:
			print(f"  Trang {i + 1}: Kiểm tra {len(annotations_on_page)} annotation(s)...")
			compare_pages_lasolution(
				ref_page, final_page, i, annotations_on_page, client
			)

	# Lưu kết quả
	if output_path is None:
		base = final_path.rsplit(".", 1)[0]
		output_path = base + "_mode2_lasolution_diff.pdf"

	final_doc.save(output_path)
	ref_doc.close()
	final_doc.close()
	print(f"Đã lưu PDF đã annotate vào: {output_path}")


if __name__ == "__main__":
	if len(sys.argv) < 3:
		print("Usage: python tool_compare_lasolution_2026.py <PDF_with_annotations.pdf> <FINAL.pdf> [output.pdf]")
		print("\nExample:")
		print("  python tool_compare_lasolution_2026.py popup_laosolution.pdf final.pdf")
		print("\nNote: Cần cập nhật OPENAI_API_KEY trong code.")
		sys.exit(1)

	ref = sys.argv[1]
	final = sys.argv[2]
	out = sys.argv[3] if len(sys.argv) > 3 else None
	main(ref, final, out)
