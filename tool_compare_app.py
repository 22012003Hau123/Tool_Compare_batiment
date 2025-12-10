import os
import sys
import tkinter as tk
from tkinter import ttk, messagebox
import threading

import fitz  # PyMuPDF

from tkinterdnd2 import TkinterDnD  # type: ignore


class ToolCompareModeUI:
	"""
	Thanh chọn 'mode' cho 3 loại PDF trong Tool_Compare, thêm phía trên
	UI gốc của PDF-Diff-Viewer mà không sửa code bên trong nó.
	"""

	def __init__(self, master: tk.Tk, pdf_app, initial_mode: str = "PAGES_LASOLUTION"):
		self.master = master
		self.pdf_app = pdf_app
		self.mode = tk.StringVar(value=initial_mode)

		self._build_mode_bar()
		self._build_results_panel()

	def _build_mode_bar(self):
		frame = ttk.LabelFrame(self.master, text="Tool_Compare mode (hướng dẫn chọn file)")
		# Sẽ nằm ngay dưới thanh control chính của PDFViewerApp
		frame.pack(side=tk.TOP, fill=tk.X, padx=8, pady=(2, 4))

		# 3 mode tương ứng 3 folder
		ttk.Radiobutton(
			frame,
			text="Mode 1: PAGES-2025  ↔  PDF (final)",
			value="PAGES_2025",
			variable=self.mode,
			command=self._update_hint,
		).pack(anchor="w", padx=6, pady=1)

		ttk.Radiobutton(
			frame,
			text="Mode 2: PAGES-LaSolution-2026  ↔  PDF (final)",
			value="PAGES_LASOLUTION",
			variable=self.mode,
			command=self._update_hint,
		).pack(anchor="w", padx=6, pady=1)

		ttk.Radiobutton(
			frame,
			text="Mode 3: 0ASSEMBLAGE_PDF  ↔  PDF (final)",
			value="ASSEMBLAGE",
			variable=self.mode,
			command=self._update_hint,
		).pack(anchor="w", padx=6, pady=1)

		# Nhãn mô tả chi tiết hơn cho từng mode
		self.hint_label = ttk.Label(frame, justify="left", foreground="#444")
		self.hint_label.pack(fill=tk.X, padx=6, pady=(4, 2))
		
		# Nút "Check Annotations" chỉ hiện khi Mode 2 được chọn
		self.check_button_frame = ttk.Frame(frame)
		self.check_button = ttk.Button(
			self.check_button_frame,
			text="🔍 Check Annotations (Mode 2)",
			command=self._check_annotations_mode2,
			state=tk.DISABLED
		)
		self.check_button.pack(side=tk.LEFT, padx=6, pady=4)
		self.status_label = ttk.Label(self.check_button_frame, text="", foreground="blue")
		self.status_label.pack(side=tk.LEFT, padx=6)
		
		# Nút bật/tắt panel kết quả
		self.toggle_results_btn = ttk.Button(
			self.check_button_frame,
			text="📊 Hiện/Không hiện kết quả",
			command=self._toggle_results_panel,
			state=tk.DISABLED
		)
		self.toggle_results_btn.pack(side=tk.LEFT, padx=6, pady=4)

		self._update_hint()

	def _update_hint(self):
		mode = self.mode.get()
		# Lấy đường dẫn thư mục hiện tại (tương thích cả Windows và Linux)
		base = os.path.dirname(os.path.abspath(__file__))

		if mode == "PAGES_2025":
			text = (
				"Mode 1 – Catalogue 2025:\n"
				f"- Pane trái: mở file trong '{os.path.join(base, 'PAGES-2025')}'\n"
				f"- Pane phải: mở file final tương ứng trong '{os.path.join(base, 'PDF')}'\n"
				"→ So sánh texte giữa catalogue 2025 và product final."
			)
			self.check_button_frame.pack_forget()
		elif mode == "ASSEMBLAGE":
			text = (
				"Mode 3 – 0ASSEMBLAGE_PDF:\n"
				f"- Pane trái: mở file export brut trong '{os.path.join(base, '0ASSEMBLAGE_PDF')}'\n"
				f"- Pane phải: mở file final tương ứng trong '{os.path.join(base, 'PDF')}'\n"
				"→ Bắt lỗi thao tác graphiste: texte mất, copy nhầm, ký hiệu (w) còn sót, v.v."
			)
			self.check_button_frame.pack_forget()
		else:  # PAGES_LASOLUTION
			text = (
				"Mode 2 – PAGES-LaSolution-2026 (data client + corrections):\n"
				f"- Pane trái: mở file có popup annotations trong '{os.path.join(base, 'PAGES-LaSolution-2026')}'\n"
				f"- Pane phải: mở file final tương ứng trong '{os.path.join(base, 'PDF')}'\n"
				"→ Tự động đọc popup annotations và kiểm tra xem PDF bên phải đã được sửa theo popup chưa (dùng GPT API)."
			)
			self.check_button_frame.pack(fill=tk.X, padx=6, pady=(2, 4))
			self._update_check_button_state()
			# Hiển thị panel kết quả nếu đã có và đang bật
			if hasattr(self, 'results_frame') and hasattr(self, 'results_panel_visible') and self.results_panel_visible:
				if hasattr(self, 'results_table_frame') and len(self.results_table_frame.winfo_children()) > 0:
					self.results_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(2, 4))
			
			# Xóa các annotations so sánh tự động (từ Mode 1/3) khi chuyển sang Mode 2
			self._clear_comparison_annotations()

		self.hint_label.config(text=text)
	
	def _clear_comparison_annotations(self):
		"""Xóa các annotations so sánh tự động (PDFComparer) khi chuyển sang Mode 2."""
		try:
			# Xóa annotations từ pane 1
			if (self.pdf_app.pane1 and self.pdf_app.pane1.pdf_document and 
				not self.pdf_app.pane1.pdf_document.is_closed):
				for page_num in range(self.pdf_app.pane1.pdf_document.page_count):
					page = self.pdf_app.pane1.pdf_document.load_page(page_num)
					annots_to_delete = [
						annot for annot in page.annots()
						if annot.type[0] == fitz.PDF_ANNOT_HIGHLIGHT and 
						annot.info.get("title") == "PDFComparer"
					]
					for annot in annots_to_delete:
						try:
							page.delete_annot(annot)
						except:
							pass
			
			# Xóa annotations từ pane 2
			if (self.pdf_app.pane2 and self.pdf_app.pane2.pdf_document and 
				not self.pdf_app.pane2.pdf_document.is_closed):
				for page_num in range(self.pdf_app.pane2.pdf_document.page_count):
					page = self.pdf_app.pane2.pdf_document.load_page(page_num)
					annots_to_delete = [
						annot for annot in page.annots()
						if annot.type[0] == fitz.PDF_ANNOT_HIGHLIGHT and 
						annot.info.get("title") == "PDFComparer"
					]
					for annot in annots_to_delete:
						try:
							page.delete_annot(annot)
						except:
							pass
			
			# Refresh UI
			if self.pdf_app.pane1:
				self.pdf_app.pane1._clear_all_rendered_pages()
				self.pdf_app.pane1.schedule_render_visible_pages()
			if self.pdf_app.pane2:
				self.pdf_app.pane2._clear_all_rendered_pages()
				self.pdf_app.pane2.schedule_render_visible_pages()
		except Exception as e:
			print(f"Error clearing comparison annotations: {e}")
	
	def _build_results_panel(self):
		"""Tạo panel hiển thị kết quả kiểm tra annotations."""
		# Panel chứa kết quả
		self.results_frame = ttk.LabelFrame(
			self.master, 
			text="📊 Kết quả kiểm tra Annotations (Mode 2)"
		)
		# Ban đầu ẩn, chỉ hiện khi có kết quả
		self.results_frame.pack_forget()  # Ẩn ban đầu
		self.results_panel_visible = False  # Trạng thái hiển thị
		
		# Container với Canvas và Scrollbar để scroll
		canvas_frame = ttk.Frame(self.results_frame)
		canvas_frame.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
		
		# Canvas để scroll
		canvas = tk.Canvas(canvas_frame, highlightthickness=0)
		scrollbar_y = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
		scrollbar_x = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=canvas.xview)
		
		# Frame bên trong canvas để chứa bảng
		self.table_frame = ttk.Frame(canvas)
		canvas_window = canvas.create_window((0, 0), window=self.table_frame, anchor="nw")
		
		# Cấu hình canvas scroll
		def configure_scroll_region(event):
			canvas.configure(scrollregion=canvas.bbox("all"))
		self.table_frame.bind("<Configure>", configure_scroll_region)
		
		def configure_canvas_width(event):
			canvas_width = event.width
			canvas.itemconfig(canvas_window, width=canvas_width)
		canvas.bind("<Configure>", configure_canvas_width)
		
		canvas.configure(yscrollcommand=scrollbar_y.set, xscrollcommand=scrollbar_x.set)
		
		# Layout
		canvas.grid(row=0, column=0, sticky="nsew")
		scrollbar_y.grid(row=0, column=1, sticky="ns")
		scrollbar_x.grid(row=1, column=0, sticky="ew")
		canvas_frame.grid_rowconfigure(0, weight=1)
		canvas_frame.grid_columnconfigure(0, weight=1)
		
		# Label thống kê
		stats_frame = ttk.Frame(self.results_frame)
		stats_frame.pack(fill=tk.X, padx=6, pady=(0, 6))
		self.stats_label = ttk.Label(
			stats_frame, 
			text="", 
			foreground="blue",
			font=("Arial", 9, "bold")
		)
		self.stats_label.pack(side=tk.LEFT)
		
		# Lưu canvas để dùng sau
		self.results_canvas = canvas
		self.results_table_frame = self.table_frame
	
	def _toggle_results_panel(self):
		"""Bật/tắt hiển thị panel kết quả."""
		if not hasattr(self, 'results_frame'):
			return
		
		if self.results_panel_visible:
			# Ẩn panel
			self.results_frame.pack_forget()
			self.results_panel_visible = False
			self.toggle_results_btn.config(text="📊 Hiện kết quả")
		else:
			# Hiện panel nếu có dữ liệu
			if hasattr(self, 'results_table_frame') and len(self.results_table_frame.winfo_children()) > 0:
				self.results_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(2, 4))
				self.results_panel_visible = True
				self.toggle_results_btn.config(text="📊 Ẩn kết quả")
			else:
				messagebox.showinfo("Info", "Chưa có kết quả để hiển thị. Vui lòng chạy 'Check Annotations' trước.")
	
	def _update_check_button_state(self):
		"""Cập nhật trạng thái nút Check dựa trên việc có file được load không."""
		pane1_ready = (
			self.pdf_app.pane1 and 
			self.pdf_app.pane1.pdf_document and 
			not self.pdf_app.pane1.pdf_document.is_closed
		)
		pane2_ready = (
			self.pdf_app.pane2 and 
			self.pdf_app.pane2.pdf_document and 
			not self.pdf_app.pane2.pdf_document.is_closed
		)
		
		if pane1_ready and pane2_ready:
			self.check_button.config(state=tk.NORMAL)
			if hasattr(self, 'toggle_results_btn'):
				self.toggle_results_btn.config(state=tk.NORMAL)
		else:
			self.check_button.config(state=tk.DISABLED)
			if hasattr(self, 'toggle_results_btn'):
				self.toggle_results_btn.config(state=tk.DISABLED)
	
	def _check_annotations_mode2(self):
		"""Kiểm tra annotations từ pane trái và so sánh với pane phải."""
		# Lấy file paths từ các pane
		pane1 = self.pdf_app.pane1
		pane2 = self.pdf_app.pane2
		
		if not pane1 or not pane1.pdf_document or pane1.pdf_document.is_closed:
			messagebox.showerror("Error", "Vui lòng mở file PDF ở pane trái (có popup annotations)")
			return
		
		if not pane2 or not pane2.pdf_document or pane2.pdf_document.is_closed:
			messagebox.showerror("Error", "Vui lòng mở file PDF ở pane phải (file final cần kiểm tra)")
			return
		
		# Lấy đường dẫn file từ pdf_document.name
		try:
			ref_path = pane1.pdf_document.name
			final_path = pane2.pdf_document.name
		except Exception as e:
			messagebox.showerror("Error", f"Không thể lấy đường dẫn file: {e}")
			return
		
		if not os.path.exists(ref_path):
			messagebox.showerror("Error", f"File không tồn tại: {ref_path}")
			return
		
		if not os.path.exists(final_path):
			messagebox.showerror("Error", f"File không tồn tại: {final_path}")
			return
		
		# Chạy kiểm tra trong thread riêng để không block UI
		self.status_label.config(text="Đang kiểm tra...", foreground="blue")
		self.check_button.config(state=tk.DISABLED)
		
		# Xóa kết quả cũ
		if hasattr(self, 'results_table_frame'):
			for widget in self.results_table_frame.winfo_children():
				widget.destroy()
		
		def run_check():
			try:
				# Import module kiểm tra
				sys.path.insert(0, os.path.dirname(__file__))
				from tool_compare_lasolution_2026 import (
					extract_popup_annotations,
					get_text_around_annotation,
					check_annotation_with_gpt,
					get_openai_client,
					GPT_MODEL,
					compare_pages_lasolution
				)
				
				# Đọc annotations
				annotations = extract_popup_annotations(ref_path)
				if not annotations:
					self.master.after(0, lambda: messagebox.showinfo(
						"Info", 
						"Không tìm thấy popup annotations nào trong file bên trái."
					))
					return
				
				# Khởi tạo GPT client
				client = get_openai_client()
				if not client:
					self.master.after(0, lambda: messagebox.showerror(
						"Error",
						"Không thể khởi tạo OpenAI client. Vui lòng kiểm tra OPENAI_API_KEY trong code."
					))
					return
				
				# Nhóm annotations theo trang
				annotations_by_page = {}
				for ann in annotations:
					page_num = ann["page"]
					if page_num not in annotations_by_page:
						annotations_by_page[page_num] = []
					annotations_by_page[page_num].append(ann)
				
				# Sử dụng PDF document đang mở trong pane2 (final)
				final_doc = pane2.pdf_document
				ref_doc = fitz.open(ref_path)
				
				# Xử lý từng trang
				num_pages = min(ref_doc.page_count, final_doc.page_count)
				total_checked = 0
				implemented_count = 0
				not_implemented_count = 0
				partial_count = 0
				unclear_count = 0
				
				# Lưu tất cả kết quả
				all_results_data = []
				
				for i in range(num_pages):
					if i in annotations_by_page:
						ref_page = ref_doc.load_page(i)
						final_page = final_doc.load_page(i)
						annotations_on_page = annotations_by_page[i]
						
						# Kiểm tra từng annotation và lưu kết quả
						for ann_data in annotations_on_page:
							annotation_content = ann_data["content"]
							rect = ann_data["rect"]
							
							current_text = get_text_around_annotation(final_page, rect, context_size=200)
							context_text = get_text_around_annotation(final_page, rect, context_size=400)
							
							result = check_annotation_with_gpt(
								client=client,
								annotation_content=annotation_content,
								current_text=current_text,
								context_text=context_text,
								model=GPT_MODEL
							)
							
							total_checked += 1
							if result["status"] == "implemented":
								implemented_count += 1
							elif result["status"] == "not_implemented":
								not_implemented_count += 1
							elif result["status"] == "partial":
								partial_count += 1
							else:
								unclear_count += 1
							
							# Lưu kết quả để hiển thị (bao gồm đầy đủ 4 nội dung)
							all_results_data.append({
								"page": i + 1,
								"status": result["status"],
								"implemented": result["implemented"],
								"reasoning": result.get("reasoning", ""),
								"evidence": result.get("evidence", ""),
								"annotation": annotation_content
							})
				
				# Hiển thị tất cả kết quả vào UI một lần
				self.master.after(0, lambda: self._display_results(all_results_data))
				
				ref_doc.close()
				
				# Hiển thị thống kê tổng
				self.master.after(0, lambda: self._display_summary(
					total_checked, implemented_count, not_implemented_count, 
					partial_count, unclear_count
				))
				
				# Hiển thị panel kết quả nếu đang bật
				self.master.after(0, lambda: self._show_results_panel_if_enabled())
				
				self.master.after(0, lambda: self.status_label.config(
					text=f"Đã kiểm tra {total_checked} annotation(s)", 
					foreground="green"
				))
			except Exception as e:
				error_msg = f"Lỗi khi kiểm tra: {str(e)}"
				self.master.after(0, lambda: messagebox.showerror("Error", error_msg))
				self.master.after(0, lambda: self.status_label.config(
					text="Lỗi", 
					foreground="red"
				))
			finally:
				self.master.after(0, lambda: self.check_button.config(state=tk.NORMAL))
		
		thread = threading.Thread(target=run_check, daemon=True)
		thread.start()
	
	def _display_results(self, results_data):
		"""Hiển thị kết quả vào bảng với text wrap trong mỗi cột."""
		if not hasattr(self, 'results_table_frame'):
			return
		
		try:
			# Xóa nội dung cũ
			for widget in self.results_table_frame.winfo_children():
				widget.destroy()
			
			# Định nghĩa cột
			columns = ["Trang", "Trạng thái", "Đã thực hiện", "Lý do", "Dẫn chứng cụ thể", "Nội dung Annotation"]
			column_widths = [60, 120, 100, 250, 300, 250]
			
			# Tạo header
			row = 0
			for col_idx, (col_name, width) in enumerate(zip(columns, column_widths)):
				header_label = tk.Label(
					self.results_table_frame,
					text=col_name,
					font=("Arial", 9, "bold"),
					bg="#e0e0e0",
					relief=tk.RAISED,
					borderwidth=1,
					width=width // 8,  # Approximate character width
					wraplength=width,
					anchor=tk.W,
					justify=tk.LEFT
				)
				header_label.grid(row=row, column=col_idx, sticky="nsew", padx=1, pady=1)
			
			# Cấu hình cột weights
			for col_idx in range(len(columns)):
				self.results_table_frame.grid_columnconfigure(col_idx, weight=1, minsize=column_widths[col_idx])
			
			row += 1
			
			# Hiển thị từng kết quả
			for data in results_data:
				status_text = {
					"implemented": "✅ Đã thực hiện",
					"not_implemented": "❌ Chưa thực hiện",
					"partial": "⚠️ Thực hiện một phần",
					"unclear": "❓ Không rõ ràng"
				}.get(data["status"], data["status"])
				
				# Xác định màu nền
				if data["status"] == "implemented":
					bg_color = "#d4edda"
					fg_color = "#155724"
				elif data["status"] == "not_implemented":
					bg_color = "#f8d7da"
					fg_color = "#721c24"
				elif data["status"] == "partial":
					bg_color = "#fff3cd"
					fg_color = "#856404"
				else:
					bg_color = "#e2e3e5"
					fg_color = "#383d41"
				
				# Lấy dữ liệu đầy đủ
				implemented_text = "✅ Có" if data.get("implemented", False) else "❌ Không"
				reasoning_text = data.get("reasoning", "")
				evidence_text = data.get("evidence", "")
				annotation_text = data.get("annotation", "")
				
				# Tạo các cell với text wrap
				cell_data = [
					str(data['page']),
					status_text,
					implemented_text,
					reasoning_text,
					evidence_text,
					annotation_text
				]
				
				for col_idx, (cell_text, width) in enumerate(zip(cell_data, column_widths)):
					cell_label = tk.Label(
						self.results_table_frame,
						text=cell_text,
						font=("Arial", 9),
						bg=bg_color,
						fg=fg_color,
						relief=tk.SUNKEN,
						borderwidth=1,
						wraplength=width,  # Cho phép wrap text
						anchor=tk.NW,  # Căn trên trái
						justify=tk.LEFT,
						padx=5,
						pady=5
					)
					cell_label.grid(row=row, column=col_idx, sticky="nsew", padx=1, pady=1)
				
				row += 1
			
			# Cập nhật scroll region
			self.results_table_frame.update_idletasks()
			self.results_canvas.configure(scrollregion=self.results_canvas.bbox("all"))
			
		except Exception as e:
			print(f"Error displaying results: {e}")
			import traceback
			traceback.print_exc()
	
	def _show_results_panel_if_enabled(self):
		"""Hiển thị panel kết quả nếu đang được bật."""
		if hasattr(self, 'results_panel_visible') and self.results_panel_visible:
			# Kiểm tra xem có nội dung không
			if hasattr(self, 'results_table_frame') and len(self.results_table_frame.winfo_children()) > 0:
				self.results_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(2, 4))
				self.toggle_results_btn.config(text="📊 Ẩn kết quả")
		else:
			# Tự động bật panel khi có kết quả mới
			if hasattr(self, 'results_table_frame') and len(self.results_table_frame.winfo_children()) > 0:
				self.results_frame.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=8, pady=(2, 4))
				self.results_panel_visible = True
				self.toggle_results_btn.config(text="📊 Ẩn kết quả")
	
	def _display_summary(self, total, implemented, not_implemented, partial, unclear):
		"""Hiển thị thống kê tổng."""
		stats_text = (
			f"Tổng cộng: {total} annotation(s) | "
			f"✅ {implemented} | "
			f"❌ {not_implemented} | "
			f"⚠️ {partial} | "
			f"❓ {unclear}"
		)
		self.stats_label.config(text=stats_text)


def launch_with_mode(initial_mode: str = "PAGES_LASOLUTION"):
	"""
	Dùng chung cho tất cả launcher: chạy PDF-Diff-Viewer gốc để xem highlight
	trực tiếp trên PDF, và đặt mode mặc định theo tham số.
	"""
	# Thêm thư mục PDF-Diff-Viewer vào sys.path
	# Thử nhiều đường dẫn có thể (hỗ trợ cả Linux và Windows)
	current_dir = os.path.dirname(os.path.abspath(__file__))
	
	possible_paths = [
		"/home/hault/PDF-Diff-Viewer",  # Đường dẫn Linux gốc
		os.path.join(current_dir, "PDF-Diff-Viewer"),  # Tương đối với script
		os.path.join(current_dir, "..", "PDF-Diff-Viewer"),  # Thư mục cha
		os.path.join(os.path.expanduser("~"), "PDF-Diff-Viewer"),  # Home directory
	]
	
	# Nếu chạy từ executable (PyInstaller)
	if hasattr(sys, '_MEIPASS'):
		possible_paths.insert(0, os.path.join(sys._MEIPASS, "PDF-Diff-Viewer"))
	
	base_dir = None
	for path in possible_paths:
		path = os.path.normpath(path)  # Chuẩn hóa đường dẫn cho Windows
		if os.path.exists(path):
			base_dir = path
			break
	
	if base_dir and os.path.exists(base_dir) and base_dir not in sys.path:
		sys.path.insert(0, base_dir)
		print(f"✅ Đã tìm thấy PDF-Diff-Viewer tại: {base_dir}")
	elif not base_dir or not os.path.exists(base_dir):
		print(f"⚠️  Warning: Không tìm thấy PDF-Diff-Viewer!")
		print(f"   Đã thử các đường dẫn: {possible_paths[:3]}")
		print("   Vui lòng đảm bảo thư mục PDF-Diff-Viewer tồn tại.")
		print("   Ứng dụng có thể không hoạt động đúng.")

	import pdf_viewer_app as pdv  # noqa: E402

	# Tạo root TkinterDnD và khởi động app gốc
	root = TkinterDnD.Tk()
	app = pdv.PDFViewerApp(root)

	# Quan trọng: gán global `app` trong module pdf_viewer_app để
	# các hàm helper (như extract_words_with_styles) dùng được.
	pdv.app = app

	# Thêm UI chọn mode cho Tool_Compare với mode mặc định
	mode_ui = ToolCompareModeUI(root, app, initial_mode=initial_mode)
	
	# Hook vào sự kiện load PDF để cập nhật trạng thái nút Check
	def on_pdf_load_hook():
		if mode_ui.mode.get() == "PAGES_LASOLUTION":
			mode_ui._update_check_button_state()
	
	# Override hàm perform_comparison_if_ready để:
	# - Mode 2: Không tự động tô màu, chỉ hiển thị kết quả trong panel
	# - Mode 1 và Mode 3: Giữ nguyên chức năng so sánh tự động
	original_perform = app.perform_comparison_if_ready
	def perform_comparison_with_update():
		current_mode = mode_ui.mode.get()
		
		# Mode 2: Không tự động so sánh và tô màu
		if current_mode == "PAGES_LASOLUTION":
			# Chỉ cập nhật button state, không chạy so sánh tự động
			on_pdf_load_hook()
			# Cập nhật UI state mà không so sánh
			doc1_ready = app.pdf_documents[0] and not app.pdf_documents[0].is_closed if app.pdf_documents[0] else False
			doc2_ready = app.pdf_documents[1] and not app.pdf_documents[1].is_closed if app.pdf_documents[1] else False
			if doc1_ready and doc2_ready:
				app.update_ui_state()
		else:
			# Mode 1 và Mode 3: Chạy so sánh tự động như bình thường
			original_perform()
			on_pdf_load_hook()
	
	app.perform_comparison_if_ready = perform_comparison_with_update

	root.protocol("WM_DELETE_WINDOW", app.on_closing)
	root.mainloop()


def main():
	# Launcher mặc định: mode LaSolution (hay dùng nhất)
	launch_with_mode("PAGES_LASOLUTION")


if __name__ == "__main__":
	main()

