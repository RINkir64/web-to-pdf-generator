import os
import sys
import time
import base64
import threading
import concurrent.futures
from urllib.parse import urlparse, urljoin
import tkinter as tk
from tkinter import ttk, messagebox, filedialog

import requests
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright
from PyPDF2 import PdfMerger
import pypandoc
import shutil

TRANSLATIONS = {
    "ja": {
        "app_title": "Web to eBook Generator",
        "url_label": "URL:",
        "fetch_btn": "候補URLを取得",
        "child_only": "子URLに限定",
        "clean_page": "ヘッダーとフッターを非表示にしてレイアウトを最適化",
        "select_all": "すべて選択",
        "deselect_all": "すべて解除",
        "col_select": "選択",
        "col_title": "タイトル",
        "col_url": "URL",
        "jobs_label": "ジョブ（進行状況）",
        "init_status": "URLを入力して「候補URLを取得」をクリックしてください。",
        "title_label": "タイトル:",
        "output_label": "出力先:",
        "browse_btn": "参照...",
        "workers_label": "並列数:",
        "format_label": "出力形式: ",
        "convert_btn": "変換して保存",
        "cancel_btn": "キャンセル",
        "waiting": "待機中...",
        "error": "エラー發生",
        "done": "完了",
        "cancelled": "キャンセルされました",
        "canceling": "キャンセルしています...",
        "input_error": "URLを入力してください。",
        "input_error_title": "入力エラー",
        "fetch_err_title": "取得エラー",
        "fetching": "「{url}」から候補を抽出しています...",
        "fetch_failed": "URLの取得に失敗しました:\n{e}",
        "found_urls": "{count}件のURL候補が見つかりました。",
        "no_url_warn": "変換するURLが選択されていません。",
        "converting_msg": "{count}件のページを{format}に変換中...",
        "pdf_converting": "PDF変換中 ({completed}/{total} 完了)...",
        "pdf_merging": "PDFを結合中...",
        "html_fetching": "HTML取得中 ({completed}/{total} 完了)...",
        "epub_generating": "EPUBを生成中...",
        "completed_msg": "{format}の生成が完了しました。\n保存先: {path}",
        "error_msg": "変換中にエラーが発生しました:\n{e}",
        "lang_label": "Lang:",
    },
    "en": {
        "app_title": "Web to eBook Generator",
        "url_label": "URL:",
        "fetch_btn": "Fetch URLs",
        "child_only": "Child URLs only",
        "clean_page": "Hide header/footer and optimize layout",
        "select_all": "Select All",
        "deselect_all": "Deselect All",
        "col_select": "Select",
        "col_title": "Title",
        "col_url": "URL",
        "jobs_label": "Jobs (Progress)",
        "init_status": "Enter URL and click 'Fetch URLs'.",
        "title_label": "Title:",
        "output_label": "Output:",
        "browse_btn": "Browse...",
        "workers_label": "Workers:",
        "format_label": "Format: ",
        "convert_btn": "Convert & Save",
        "cancel_btn": "Cancel",
        "waiting": "Waiting...",
        "error": "Error",
        "done": "Done",
        "cancelled": "Cancelled",
        "canceling": "Cancelling...",
        "input_error": "Please enter a URL.",
        "input_error_title": "Input Error",
        "fetch_err_title": "Fetch Error",
        "fetching": "Extracting candidates from '{url}'...",
        "fetch_failed": "Failed to fetch URL:\n{e}",
        "found_urls": "Found {count} candidate URLs.",
        "no_url_warn": "No URLs selected for conversion.",
        "converting_msg": "Converting {count} pages to {format}...",
        "pdf_converting": "Converting PDF ({completed}/{total} done)...",
        "pdf_merging": "Merging PDFs...",
        "html_fetching": "Fetching HTML ({completed}/{total} done)...",
        "epub_generating": "Generating EPUB...",
        "completed_msg": "Generation of {format} completed.\nSaved to: {path}",
        "error_msg": "An error occurred during conversion:\n{e}",
        "lang_label": "Lang:",
    }
}

class JobFrame(ttk.Frame):
    def __init__(self, master, job_title, cancel_cmd, tr_func):
        super().__init__(master, relief=tk.GROOVE, borderwidth=2, padding=5)
        self.columnconfigure(0, weight=1)
        self.tr = tr_func
        
        self.title_lbl = ttk.Label(self, text=job_title, font=("", 10, "bold"), anchor="w")
        self.title_lbl.grid(row=0, column=0, sticky="ew", pady=(0,5))
        
        self.progress_var = tk.DoubleVar(value=0)
        self.progress_bar = ttk.Progressbar(self, mode="determinate", variable=self.progress_var)
        self.progress_bar.grid(row=1, column=0, sticky="ew")
        
        self.status_var = tk.StringVar(value=self.tr("waiting"))
        self.status_lbl = ttk.Label(self, textvariable=self.status_var, font=("", 9), anchor="w")
        self.status_lbl.grid(row=2, column=0, sticky="ew", pady=(2,0))
        
        self.cancel_btn = ttk.Button(self, text=self.tr("cancel_btn"), command=cancel_cmd)
        self.cancel_btn.grid(row=0, column=1, rowspan=3, padx=(5,0), sticky="ns")

    def update_progress(self, progress, status):
        self.progress_var.set(progress)
        self.status_var.set(status)

class EbookGeneratorApp:
    def __init__(self, root):
        self.root = root
        
        self.candidates = []
        self.driver = None
        self.url_selections = {}
        self.jobs_lock = threading.Lock()
        
        # Current Language State
        self.lang_var = tk.StringVar(value="ja")
        
        # Variable traces that trigger extension updates
        self.title_var = tk.StringVar(value="Web to eBook")
        self.output_path_var = tk.StringVar(value=os.path.abspath("Final_eBook.pdf"))
        self.format_var = tk.StringVar(value="PDF")
        
        self.child_only_var = tk.BooleanVar(value=True)
        self.clean_page_var = tk.BooleanVar(value=True)
        self.url_var = tk.StringVar()
        self.status_var = tk.StringVar(value=self.tr("init_status"))
        self.workers_var = tk.IntVar(value=min(4, os.cpu_count() or 4))
        
        self.setup_ui()
        self.lang_var.trace_add("write", lambda *args: self.update_texts())

    def tr(self, key, **kwargs):
        lang = self.lang_var.get()
        text = TRANSLATIONS.get(lang, TRANSLATIONS["ja"]).get(key, key)
        if kwargs:
            try:
                return text.format(**kwargs)
            except KeyError:
                pass
        return text

    def setup_ui(self):
        self.root.title(self.tr("app_title"))
        self.root.geometry("900x600")
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        
        self.paned = ttk.PanedWindow(self.root, orient=tk.HORIZONTAL)
        self.paned.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.left_side = ttk.Frame(self.paned)
        self.paned.add(self.left_side, weight=2)
        self.left_side.columnconfigure(0, weight=1)
        self.left_side.rowconfigure(1, weight=1)
        
        self.right_side = ttk.Frame(self.paned, padding=5)
        self.paned.add(self.right_side, weight=1)
        self.right_side.columnconfigure(0, weight=1)
        self.right_side.rowconfigure(1, weight=1)
        
        self.jobs_lbl = ttk.Label(self.right_side, text=self.tr("jobs_label"), font=("", 12, "bold"))
        self.jobs_lbl.grid(row=0, column=0, sticky="w", pady=(0, 5))
        
        self.jobs_canvas = tk.Canvas(self.right_side)
        self.jobs_scrollbar = ttk.Scrollbar(self.right_side, orient="vertical", command=self.jobs_canvas.yview)
        self.jobs_scrollable_frame = ttk.Frame(self.jobs_canvas)
        
        self.jobs_scrollable_frame.bind("<Configure>", lambda e: self.jobs_canvas.configure(scrollregion=self.jobs_canvas.bbox("all")))
        self.jobs_canvas_window = self.jobs_canvas.create_window((0, 0), window=self.jobs_scrollable_frame, anchor="nw")
        self.jobs_canvas.configure(yscrollcommand=self.jobs_scrollbar.set)
        
        self.jobs_canvas.grid(row=1, column=0, sticky="nsew")
        self.jobs_scrollbar.grid(row=1, column=1, sticky="ns")
        self.jobs_canvas.bind("<Configure>", lambda e: self.jobs_canvas.itemconfig(self.jobs_canvas_window, width=e.width))

        # TOP FRAME
        top_frame = ttk.Frame(self.left_side, padding="10")
        top_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        top_frame.columnconfigure(2, weight=1)
        
        self.lang_lbl = ttk.Label(top_frame, text=self.tr("lang_label"))
        self.lang_lbl.grid(row=0, column=0, padx=5, sticky=tk.W)
        self.lang_combo = ttk.Combobox(top_frame, textvariable=self.lang_var, values=["ja", "en"], width=5, state="readonly")
        self.lang_combo.grid(row=0, column=1, padx=5, sticky=tk.W)
        
        self.url_lbl = ttk.Label(top_frame, text=self.tr("url_label"))
        self.url_lbl.grid(row=1, column=0, padx=5, pady=5)
        self.url_entry = ttk.Entry(top_frame, textvariable=self.url_var)
        self.url_entry.grid(row=1, column=1, columnspan=2, sticky=(tk.W, tk.E), padx=5, pady=5)
        
        self.fetch_btn = ttk.Button(top_frame, text=self.tr("fetch_btn"), command=self.fetch_urls)
        self.fetch_btn.grid(row=1, column=3, padx=5, pady=5)
        
        options_frame = ttk.Frame(top_frame)
        options_frame.grid(row=2, column=1, columnspan=3, sticky=(tk.W, tk.E), pady=5)
        
        self.child_only_chk = ttk.Checkbutton(options_frame, text=self.tr("child_only"), variable=self.child_only_var)
        self.child_only_chk.pack(side=tk.LEFT, padx=5)
        
        self.clean_page_chk = ttk.Checkbutton(options_frame, text=self.tr("clean_page"), variable=self.clean_page_var)
        self.clean_page_chk.pack(side=tk.LEFT, padx=5)
        
        # MID FRAME (Treeview)
        mid_frame = ttk.Frame(self.left_side, padding="10")
        mid_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        mid_frame.columnconfigure(0, weight=1)
        mid_frame.rowconfigure(1, weight=1)
        
        ctrl_frame = ttk.Frame(mid_frame)
        ctrl_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=5)
        self.sel_all_btn = ttk.Button(ctrl_frame, text=self.tr("select_all"), command=self.select_all)
        self.sel_all_btn.pack(side=tk.LEFT, padx=5)
        self.desel_all_btn = ttk.Button(ctrl_frame, text=self.tr("deselect_all"), command=self.deselect_all)
        self.desel_all_btn.pack(side=tk.LEFT, padx=5)
        
        columns = ("#", "タイトル", "URL")
        self.tree = ttk.Treeview(mid_frame, columns=columns, show="headings", selectmode="none")
        self.tree.heading("#", text=self.tr("col_select"))
        self.tree.column("#", width=50, stretch=False, anchor="center")
        self.tree.heading("タイトル", text=self.tr("col_title"))
        self.tree.column("タイトル", width=300, anchor="w")
        self.tree.heading("URL", text=self.tr("col_url"))
        self.tree.column("URL", width=400, anchor="w")
        self.tree.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        scrollbar = ttk.Scrollbar(mid_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscroll=scrollbar.set)
        scrollbar.grid(row=1, column=1, sticky=(tk.N, tk.S))
        self.tree.bind('<Button-1>', self.on_tree_click)
        
        # BOTTOM FRAME
        bottom_frame = ttk.Frame(self.left_side, padding="10")
        bottom_frame.grid(row=2, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        bottom_frame.columnconfigure(0, weight=1)
        
        self.status_label = ttk.Label(bottom_frame, textvariable=self.status_var)
        self.status_label.grid(row=0, column=0, sticky=tk.W, columnspan=2)
        
        settings_frame = ttk.Frame(bottom_frame)
        settings_frame.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=5, columnspan=2)
        settings_frame.columnconfigure(1, weight=1)
        
        self.title_lbl2 = ttk.Label(settings_frame, text=self.tr("title_label"))
        self.title_lbl2.grid(row=0, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(settings_frame, textvariable=self.title_var).grid(row=0, column=1, sticky=(tk.W, tk.E), padx=5, pady=2, columnspan=2)
        
        self.output_lbl2 = ttk.Label(settings_frame, text=self.tr("output_label"))
        self.output_lbl2.grid(row=1, column=0, sticky=tk.W, padx=5, pady=2)
        ttk.Entry(settings_frame, textvariable=self.output_path_var).grid(row=1, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        self.browse_btn = ttk.Button(settings_frame, text=self.tr("browse_btn"), command=self.browse_output_path)
        self.browse_btn.grid(row=1, column=2, padx=5, pady=2)
        
        self.worker_lbl = ttk.Label(settings_frame, text=self.tr("workers_label"))
        self.worker_lbl.grid(row=2, column=0, sticky=tk.W, padx=5, pady=2)
        workers_slider = ttk.Scale(settings_frame, from_=1, to=8, orient=tk.HORIZONTAL, variable=self.workers_var, command=lambda v: self.workers_var.set(int(float(v))))
        workers_slider.grid(row=2, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)
        ttk.Label(settings_frame, textvariable=self.workers_var).grid(row=2, column=2, sticky=tk.W, padx=5)

        format_frame = ttk.Frame(bottom_frame)
        format_frame.grid(row=3, column=0, sticky=tk.W, pady=5)
        self.fmt_lbl = ttk.Label(format_frame, text=self.tr("format_label"))
        self.fmt_lbl.pack(side=tk.LEFT)
        self.radio_epub = ttk.Radiobutton(format_frame, text="EPUB", variable=self.format_var, value="EPUB", command=self.update_extension)
        self.radio_epub.pack(side=tk.LEFT, padx=5)
        self.radio_pdf = ttk.Radiobutton(format_frame, text="PDF", variable=self.format_var, value="PDF", command=self.update_extension)
        self.radio_pdf.pack(side=tk.LEFT, padx=5)
        
        self.convert_btn_ui = ttk.Button(bottom_frame, text=self.tr("convert_btn"), command=self.start_conversion)
        self.convert_btn_ui.grid(row=3, column=1, pady=5, sticky=tk.E)
        self.update_extension()

    def update_texts(self):
        self.root.title(self.tr("app_title"))
        self.fetch_btn.config(text=self.tr("fetch_btn"))
        self.url_lbl.config(text=self.tr("url_label"))
        self.child_only_chk.config(text=self.tr("child_only"))
        self.clean_page_chk.config(text=self.tr("clean_page"))
        self.sel_all_btn.config(text=self.tr("select_all"))
        self.desel_all_btn.config(text=self.tr("deselect_all"))
        self.tree.heading("#", text=self.tr("col_select"))
        self.tree.heading("タイトル", text=self.tr("col_title"))
        self.tree.heading("URL", text=self.tr("col_url"))
        self.jobs_lbl.config(text=self.tr("jobs_label"))
        self.title_lbl2.config(text=self.tr("title_label"))
        self.output_lbl2.config(text=self.tr("output_label"))
        self.browse_btn.config(text=self.tr("browse_btn"))
        self.worker_lbl.config(text=self.tr("workers_label"))
        self.fmt_lbl.config(text=self.tr("format_label"))
        self.convert_btn_ui.config(text=self.tr("convert_btn"))
        self.lang_lbl.config(text=self.tr("lang_label"))

    def browse_output_path(self):
        ext = ".epub" if self.format_var.get() == "EPUB" else ".pdf"
        filetypes = [("EPUB files", "*.epub")] if ext == ".epub" else [("PDF files", "*.pdf")]
        initialfile = "Final_eBook" + ext
        if self.title_var.get() != "Web to eBook" and self.title_var.get() != "":
            initialfile = self.title_var.get() + ext
        path = filedialog.asksaveasfilename(defaultextension=ext, filetypes=filetypes, initialfile=initialfile)
        if path:
            self.output_path_var.set(path)

    def update_extension(self):
        current_path = self.output_path_var.get()
        if not current_path:
            return
        base, _ = os.path.splitext(current_path)
        ext = ".epub" if self.format_var.get() == "EPUB" else ".pdf"
        self.output_path_var.set(base + ext)

    def on_tree_click(self, event):
        region = self.tree.identify("region", event.x, event.y)
        if region == "cell":
            column = self.tree.identify_column(event.x)
            if column == '#1': 
                item = self.tree.identify_row(event.y)
                if item:
                    current_val = self.tree.set(item, "#")
                    new_val = "☐" if current_val == "☑" else "☑"
                    self.tree.set(item, "#", new_val)
                    self.url_selections[item] = (new_val == "☑")

    def select_all(self):
        for item in self.tree.get_children():
            self.tree.set(item, "#", "☑")
            self.url_selections[item] = True

    def deselect_all(self):
        for item in self.tree.get_children():
            self.tree.set(item, "#", "☐")
            self.url_selections[item] = False

    def fetch_urls(self):
        base_url = self.url_var.get().strip()
        if not base_url:
            messagebox.showwarning(self.tr("input_error_title"), self.tr("input_error"))
            return
            
        self.fetch_btn.config(state="disabled")
        self.status_var.set(self.tr("fetching", url=base_url))
        
        child_only = self.child_only_var.get()
        threading.Thread(target=self._fetch_thread, args=(base_url, child_only), daemon=True).start()

    def _fetch_thread(self, base_url, child_only):
        try:
            response = requests.get(base_url, timeout=10)
            response.raise_for_status()
            
            soup = BeautifulSoup(response.text, "html.parser")
            parsed_base = urlparse(base_url)
            
            candidates = []
            seen = set()
            
            base_url_normalized = base_url.rstrip("/")
            seen.add(base_url)
            seen.add(base_url_normalized)
            seen.add(base_url_normalized + "/")
            
            for a_tag in soup.find_all("a", href=True):
                href = a_tag["href"].split("#")[0]
                if not href: continue
                    
                full_url = urljoin(base_url, href)
                parsed_url = urlparse(full_url)
                
                if parsed_url.netloc == parsed_base.netloc:
                    if child_only and not full_url.startswith(base_url): continue
                    if full_url not in seen:
                        seen.add(full_url)
                        title = a_tag.get_text(strip=True) or href
                        candidates.append((full_url, title))
            
            self.root.after(0, self._update_treeview, candidates)
            
        except Exception as e:
            self.root.after(0, self._show_error, self.tr("fetch_failed", e=e), self.tr("fetch_err_title"))
        finally:
            self.root.after(0, lambda: self.fetch_btn.config(state="normal"))

    def _update_treeview(self, candidates):
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.candidates = candidates
        self.url_selections.clear()
        
        for url, title in candidates:
            item_id = self.tree.insert("", "end", values=("☑", title, url))
            self.url_selections[item_id] = True
            
        self.status_var.set(self.tr("found_urls", count=len(candidates)))

    def _show_error(self, message, title=None):
        title = title or self.tr("error")
        messagebox.showerror(title, message)

    def start_conversion(self):
        selected_urls = []
        for item in self.tree.get_children():
            if self.url_selections.get(item, False):
                url = self.tree.item(item, "values")[2]
                selected_urls.append(url)
                
        if not selected_urls:
            messagebox.showwarning(self.tr("input_error_title"), self.tr("no_url_warn"))
            return
            
        output_format = self.format_var.get()
        clean_page = self.clean_page_var.get()
        book_title = self.title_var.get()
        output_path = self.output_path_var.get()
        
        job_cancel_event = threading.Event()
        with self.jobs_lock:
            job_frame = JobFrame(self.jobs_scrollable_frame, book_title, lambda: job_cancel_event.set(), self.tr)
            job_frame.pack(fill="x", expand=True, pady=2)
            
            def cancel_clicked():
                job_cancel_event.set()
                job_frame.cancel_btn.config(state="disabled")
                job_frame.update_progress(0, self.tr("canceling"))
            job_frame.cancel_btn.config(command=cancel_clicked)

        workers = self.workers_var.get()
        threading.Thread(target=self._conversion_thread, args=(selected_urls, output_format, clean_page, book_title, output_path, job_frame, job_cancel_event, workers), daemon=True).start()

    def _conversion_thread(self, selected_urls, output_format, clean_page, book_title, output_path, job_frame, cancel_event, max_workers):
        try:
            total = len(selected_urls)
            max_workers = min(max_workers, total)
            
            if output_format == "PDF":
                output_dir = "ebook_output"
                os.makedirs(output_dir, exist_ok=True)
                pdf_files = [None] * total
                
                def _process_single_pdf(index, url):
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        context = browser.new_context()
                        page = context.new_page()
                        pdf_path = os.path.join(output_dir, f"page_{index:03d}.pdf")
                        self._process_and_save_pdf(page, url, pdf_path, clean_page)
                        browser.close()
                        return index, pdf_path

                completed = 0
                self.root.after(0, job_frame.update_progress, 0, self.tr("pdf_converting", completed=0, total=total))
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {}
                    for i, url in enumerate(selected_urls, 1):
                        if cancel_event.is_set(): break
                        futures[executor.submit(_process_single_pdf, i, url)] = (i, url)

                    for future in concurrent.futures.as_completed(futures):
                        if cancel_event.is_set(): break
                        try:
                            idx, pdf_path = future.result()
                            pdf_files[idx - 1] = pdf_path
                        except Exception as e:
                            print(f"Error processing PDF task: {e}")
                        
                        completed += 1
                        progress = (completed / total) * 100
                        self.root.after(0, job_frame.update_progress, progress, self.tr("pdf_converting", completed=completed, total=total))
                        
                if cancel_event.is_set():
                    self.root.after(0, job_frame.update_progress, 0, self.tr("cancelled"))
                    return
                self.root.after(0, job_frame.update_progress, 100, self.tr("pdf_merging"))
                
                output_merged_pdf = output_path
                merger = PdfMerger()
                merger.add_metadata({'/Title': book_title, '/Producer': 'Web to PDF eBook Generator'})
                for pdf in pdf_files:
                    if pdf and os.path.exists(pdf): merger.append(pdf)
                merger.write(output_merged_pdf)
                merger.close()
                final_output = output_merged_pdf
                
            else: # EPUB using custom builder
                import mimetypes
                from urllib.request import urlopen
                from epub_builder import EpubBuilder

                book = EpubBuilder(title=book_title, language=self.lang_var.get())

                html_data = [None] * total
                
                def _process_single_epub(index, url):
                    with sync_playwright() as p:
                        browser = p.chromium.launch(headless=True)
                        context = browser.new_context()
                        page = context.new_page()
                        chapter_title, html_content = self._get_html_for_epub(page, url, clean_page)
                        browser.close()
                        return index, chapter_title, html_content, url

                completed = 0
                self.root.after(0, job_frame.update_progress, 0, self.tr("html_fetching", completed=0, total=total))
                
                with concurrent.futures.ThreadPoolExecutor(max_workers=max_workers) as executor:
                    futures = {}
                    for i, url in enumerate(selected_urls, 1):
                        if cancel_event.is_set(): break
                        futures[executor.submit(_process_single_epub, i, url)] = (i, url)
                        
                    for future in concurrent.futures.as_completed(futures):
                        if cancel_event.is_set(): break
                        try:
                            idx, c_title, html_content, page_url = future.result()
                            html_data[idx - 1] = (page_url, c_title, html_content)
                        except Exception as e:
                            print(f"Error processing EPUB task: {e}")
                            
                        completed += 1
                        progress = (completed / total) * 100
                        self.root.after(0, job_frame.update_progress, progress, self.tr("html_fetching", completed=completed, total=total))
                
                if cancel_event.is_set():
                    self.root.after(0, job_frame.update_progress, 0, self.tr("cancelled"))
                    return
                    
                self.root.after(0, job_frame.update_progress, 100, self.tr("epub_generating"))
                final_output = output_path
                
                image_cache = {}
                
                valid_data = [d for d in html_data if d is not None]
                for idx, (page_url, c_title, h_content) in enumerate(valid_data, 1):
                    soup = BeautifulSoup(h_content, "html.parser")
                    
                    # Convert <picture> elements to plain <img>
                    for picture in soup.find_all("picture"):
                        img_tag = picture.find("img")
                        if img_tag:
                            source = picture.find("source")
                            if source and source.get("srcset") and not img_tag.get("src"):
                                srcset_val = source["srcset"]
                                img_tag["src"] = srcset_val.split(",")[0].strip().split(" ")[0]
                            picture.replace_with(img_tag)

                    for img in soup.find_all("img"):
                        # Support lazy-loaded images gracefully
                        src = img.get("data-src") or img.get("data-original") or img.get("data-lazy-src") or img.get("src")
                        if not src or src.startswith("data:image/svg"):
                            img.decompose()
                            continue
                        
                        # Remove problematic attributes for EPUB readers
                        for attr in ["srcset", "sizes", "loading", "class", "style",
                                     "data-src", "data-original", "data-lazy-src",
                                     "data-srcset", "decoding", "fetchpriority", "width", "height"]:
                            if img.has_attr(attr):
                                del img[attr]
                                
                        abs_src = urljoin(page_url, src)
                        if abs_src not in image_cache:
                            try:
                                if abs_src.startswith("data:"):
                                    # Handle base64 data URIs
                                    import re as _re
                                    m = _re.match(r'data:([^;]+);base64,(.*)', abs_src)
                                    if m:
                                        ctype = m.group(1)
                                        img_data = base64.b64decode(m.group(2))
                                        ext = mimetypes.guess_extension(ctype) or ".png"
                                    else:
                                        with urlopen(abs_src) as response:
                                            img_data = response.read()
                                            ctype = response.headers.get_content_type()
                                            ext = mimetypes.guess_extension(ctype) or ".png"
                                else:
                                    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'}
                                    resp = requests.get(abs_src, headers=headers, timeout=15)
                                    if resp.status_code != 200:
                                        img.decompose()
                                        continue
                                    img_data = resp.content
                                    ctype = resp.headers.get("content-type", "image/jpeg").split(";")[0].strip()
                                    # Validate it's actually an image
                                    if not ctype.startswith("image/"):
                                        img.decompose()
                                        continue
                                    ext = mimetypes.guess_extension(ctype) or ".jpg"
                                    # Skip tiny tracking pixels (< 100 bytes)
                                    if len(img_data) < 100:
                                        img.decompose()
                                        continue
                                        
                                img_filename = f"images/img_{len(image_cache)}{ext}"
                                book.add_image(file_name=img_filename, content=img_data, media_type=ctype)
                                image_cache[abs_src] = img_filename
                            except Exception as e:
                                print(f"Image fetch error ({abs_src}): {e}")
                                img.decompose()
                                continue
                                
                        if abs_src in image_cache:
                            # Relative path ensures Apple Books and other strict readers display the image
                            img["src"] = image_cache[abs_src]
                            
                    book.add_chapter(file_name=f"chap_{idx:03d}.xhtml", title=c_title, content=str(soup))

                book.write(final_output)

            if not cancel_event.is_set():
                self.root.after(0, job_frame.update_progress, 100, f"{self.tr('done')}! '{os.path.basename(final_output)}'")
                self.root.after(0, lambda: job_frame.cancel_btn.config(state="disabled"))
                self.root.after(0, messagebox.showinfo, self.tr("done"), self.tr("completed_msg", format=output_format, path=os.path.abspath(final_output)))
            
        except Exception as e:
            self.root.after(0, job_frame.update_progress, 0, self.tr("error"))
            self.root.after(0, self._show_error, self.tr("error_msg", e=e))
        finally:
            pass

    def _process_and_save_pdf(self, page, url, output_path, clean_page):
        page.goto(url, wait_until="networkidle")
        
        scroll_script = """
        () => {
            return new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 100;
                const timer = setInterval(() => {
                    const scrollHeight = document.body.scrollHeight;
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if (totalHeight >= scrollHeight - window.innerHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 50);
            });
        }
        """
        try:
            page.evaluate(scroll_script)
            time.sleep(2)
        except Exception as e:
            print("Scroll failed:", e)

        mathjax_wait_script = """
        () => {
            return new Promise((resolve) => {
                if (typeof MathJax === 'undefined') {
                    resolve(true);
                    return;
                }
                if (MathJax.version && MathJax.version.startsWith('3')) {
                    if (MathJax.startup && MathJax.startup.promise) {
                        MathJax.startup.promise.then(() => resolve(true)).catch(() => resolve(true));
                    } else {
                        resolve(true);
                    }
                } else {
                    if (MathJax.Hub && MathJax.Hub.queue) {
                        MathJax.Hub.Queue(() => resolve(true));
                    } else {
                        resolve(true);
                    }
                }
            });
        }
        """
        try:
            page.evaluate(mathjax_wait_script)
        except Exception as e:
            print("MathJax wait timeout:", e)

        if clean_page:
            try:
                self._hide_header_footer(page)
                time.sleep(1)
            except Exception as e:
                print("CSS injection failed:", e)

        page.pdf(path=output_path, format="A4", print_background=True)

    def _hide_header_footer(self, page):
        hide_script = """
        () => {
            let el = document.querySelector('h1.entry-title');
            if(el) {
                while(el && el.tagName !== 'BODY') {
                    el.classList.add('safe-keep-title');
                    el = el.parentElement;
                }
            }
            
            const style = document.createElement('style');
            style.textContent = `
                header, footer, nav, aside, .sidebar, .widget, .menu, .ads, .comments, iframe, .share {
                    display: none !important;
                }
                body, main, article, .content {
                    margin: 0 !important;
                    padding: 0 !important;
                    width: 100% !important;
                    max-width: none !important;
                    font-size: 16px !important;
                    line-height: 1.6 !important;
                    background-color: white !important;
                }
                main, article, .content, #content, .container, .wrapper {
                    width: 100% !important;
                    max-width: none !important;
                    box-sizing: border-box !important;
                    float: none !important;
                    margin: 0 !important;
                }
            `;
            document.head.appendChild(style);

            const hideEmptyDivs = () => {
                document.querySelectorAll('div, section').forEach(el => {
                    if (el.classList.contains('safe-keep-title')) return;
                    if (el.querySelector('img, canvas, svg, math')) return;
                    
                    if (el.innerHTML.trim() === '' || (el.clientHeight === 0 && !el.querySelector('img'))) {
                        el.style.display = 'none';
                    }
                });
            }
            hideEmptyDivs();
            setTimeout(hideEmptyDivs, 500);

            const unstickElements = () => {
                document.querySelectorAll('*').forEach(el => {
                    const style = window.getComputedStyle(el);
                    if (style.position === 'fixed' || style.position === 'sticky') {
                        el.style.setProperty('position', 'relative', 'important');
                    }
                });
            }
            setTimeout(unstickElements, 100);
        }
        """
        page.evaluate(hide_script)

    def _get_html_for_epub(self, page, url, clean_page):
        page.goto(url, wait_until="networkidle")
        
        scroll_script = """
        () => {
            return new Promise((resolve) => {
                let totalHeight = 0;
                const distance = 100;
                const timer = setInterval(() => {
                    const scrollHeight = document.body.scrollHeight;
                    window.scrollBy(0, distance);
                    totalHeight += distance;
                    if (totalHeight >= scrollHeight - window.innerHeight) {
                        clearInterval(timer);
                        resolve();
                    }
                }, 50);
            });
        }
        """
        try:
            page.evaluate(scroll_script)
            time.sleep(2)
        except Exception as e:
            print("Scroll failed:", e)

        # Force lazy-loaded images to resolve their real src
        lazy_load_script = """
        () => {
            // Swap data-src / data-original / data-lazy-src into src
            document.querySelectorAll('img').forEach(img => {
                const lazySrc = img.getAttribute('data-src') || img.getAttribute('data-original') || img.getAttribute('data-lazy-src');
                if (lazySrc && (!img.src || img.src.includes('placeholder') || img.src.includes('data:image/svg'))) {
                    img.src = lazySrc;
                }
            });
            // Convert <picture><source> into plain <img> src
            document.querySelectorAll('picture').forEach(pic => {
                const img = pic.querySelector('img');
                if (!img) return;
                const source = pic.querySelector('source');
                if (source) {
                    const srcset = source.getAttribute('srcset');
                    if (srcset && (!img.src || img.src.includes('placeholder'))) {
                        img.src = srcset.split(',')[0].trim().split(' ')[0];
                    }
                }
            });
        }
        """
        try:
            page.evaluate(lazy_load_script)
            time.sleep(1)
        except Exception as e:
            print("Lazy-load resolve failed:", e)

        math_script = """
        () => {
            return new Promise((resolve) => {
                let checkAndConvert = () => {
                    let isReady = false;
                    if (typeof MathJax !== 'undefined') {
                        if (MathJax.version && MathJax.version.startsWith('3')) {
                            isReady = true;
                        } else if (typeof MathJax.Hub !== 'undefined') {
                            if (MathJax.Hub.queue.pending === 0) {
                                isReady = true;
                                let jax = MathJax.Hub.getAllJax();
                                for (let i = 0; i < jax.length; i++) {
                                    try {
                                        let mathml = jax[i].root.toMathML("");
                                        let span = document.createElement("span");
                                        span.innerHTML = mathml;
                                        let element = document.getElementById(jax[i].inputID + "-Frame");
                                        if(element && element.parentNode) {
                                            element.parentNode.replaceChild(span, element);
                                        }
                                    } catch(e) {}
                                }
                            }
                        }
                    } else {
                        isReady = true;
                    }
                    
                    if (isReady) {
                        resolve(true); 
                    } else {
                        setTimeout(checkAndConvert, 500);
                    }
                };
                checkAndConvert();
            });
        }
        """
        time.sleep(2)
        try:
            page.evaluate(math_script)
        except Exception as e:
            print("MathJax async timeout:", e)

        if clean_page:
            try:
                self._hide_header_footer(page)
                time.sleep(1)
            except Exception as e:
                print("CSS injection failed:", e)

        html_content = page.content()
        soup = BeautifulSoup(html_content, 'html.parser')
        title = soup.title.string if soup.title else "Unknown Title"
        body_content = soup.body.decode_contents() if soup.body else html_content
        
        if clean_page:
            clean_html = f"""
            <html>
            <head>
                <meta charset="utf-8">
                <title>{title}</title>
                <style>
                    body {{ font-family: -apple-system, sans-serif; line-height: 1.6; padding: 1em; max-width: 900px; margin: 0 auto; color: #333; }}
                    img {{ max-width: 100%; height: auto; display: block; }}
                    h1.chapter-generated-title {{ border-bottom: 2px solid #eee; padding-bottom: 0.3em; margin-bottom: 1em; }}
                    figure {{ margin: 1em 0; text-align: center; }}
                    figcaption {{ font-size: 0.9em; color: #666; margin-top: 0.5em; }}
                </style>
            </head>
            <body>
                <h1 class="chapter-generated-title">{title}</h1>
                {body_content}
            </body>
            </html>
            """
        else:
            clean_html = f"<html><head><title>{title}</title></head><body><h1 class='chapter-generated-title'>{title}</h1>{body_content}</body></html>"
            
        return title, clean_html


if __name__ == "__main__":
    root = tk.Tk()
    app = EbookGeneratorApp(root)
    root.mainloop()
