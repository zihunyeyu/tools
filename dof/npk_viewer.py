"""
NPK Viewer - NPK 文件浏览器

使用 pydoftools 库打开 NPK 文件并浏览其中的 IMG 图片。
界面布局参考专业 NPK 编辑器设计。

Usage:
    python npk_viewer.py [npk_file_path]
"""

import os
import sys
import tkinter as tk
from pathlib import Path
from tkinter import filedialog, messagebox, ttk
from typing import List, Optional, Tuple

from PIL import Image, ImageDraw, ImageTk

from pydoftools.npk import NPK


class NpkImageLoader:
    """NPK 图像加载器 - 处理 NPK 文件的加载和图像提取"""
    
    def __init__(self):
        self.npk: Optional[NPK] = None
        self.file_path: Optional[Path] = None
        self.current_img_file = None
        self.current_img = None
        self.current_sprite_index: int = 0
        self.current_palette_index: int = 0
    
    def load_npk(self, file_path: str) -> bool:
        """加载 NPK 文件"""
        try:
            with open(file_path, 'rb') as f:
                self.npk = NPK.open(f)
                self.npk.load_all()
            self.file_path = Path(file_path)
            return True
        except Exception as e:
            messagebox.showerror("错误", f"无法加载 NPK 文件:\n{e}")
            return False
    
    def get_file_list(self) -> List[Tuple[int, str, int, int]]:
        """获取 NPK 中的文件列表 (索引, 文件名, 图片数量, IMG版本)"""
        if not self.npk:
            return []
        
        files = []
        for i, npk_file in enumerate(self.npk.files):
            try:
                img = npk_file.to_img()
                img_count = len(img.images) if img.images else 0
                version = img.version
                files.append((i, npk_file.name, img_count, version))
            except Exception:
                files.append((i, npk_file.name, 0, 0))
        return files
    
    def load_img_file(self, index: int) -> bool:
        """加载指定索引的 IMG 文件"""
        if not self.npk or index < 0 or index >= len(self.npk.files):
            return False
        
        try:
            self.current_img_file = self.npk.files[index]
            self.current_img = self.current_img_file.to_img()
            self.current_sprite_index = 0
            self.current_palette_index = 0
            return True
        except Exception as e:
            messagebox.showerror("错误", f"无法加载 IMG 文件:\n{e}")
            return False
    
    def get_sprite_list(self) -> List[dict]:
        """获取当前 IMG 的所有 Sprite 信息列表"""
        if not self.current_img or not self.current_img.images:
            return []
        
        sprites = []
        for i in range(len(self.current_img.images)):
            try:
                sprite = self.current_img.image_by_index(i)
                sprites.append({
                    'index': i,
                    'width': sprite.w,
                    'height': sprite.h,
                    'format': sprite.format,
                    'x': getattr(sprite, 'x', 0),
                    'y': getattr(sprite, 'y', 0),
                })
            except Exception:
                sprites.append({
                    'index': i,
                    'width': 0,
                    'height': 0,
                    'format': 0,
                    'x': 0,
                    'y': 0,
                })
        return sprites
    
    def get_current_sprite_count(self) -> int:
        """获取当前 IMG 文件中的 Sprite 数量"""
        if not self.current_img or not self.current_img.images:
            return 0
        return len(self.current_img.images)
    
    def get_current_sprite_info(self) -> Optional[dict]:
        """获取当前 Sprite 的信息"""
        if not self.current_img or not self.current_img.images:
            return None
        
        count = self.get_current_sprite_count()
        if self.current_sprite_index >= count:
            return None
        
        sprite = self.current_img.image_by_index(self.current_sprite_index)
        return {
            'index': self.current_sprite_index,
            'count': count,
            'width': sprite.w,
            'height': sprite.h,
            'format': sprite.format,
            'x': getattr(sprite, 'x', 0),
            'y': getattr(sprite, 'y', 0),
            'img_version': self.current_img.version,
            'palette_count': self.get_palette_count(),
            'palette_index': self.current_palette_index,
        }
    
    def get_sprite_image(self, sprite_index: int) -> Optional[Image.Image]:
        """获取指定索引 Sprite 的 PIL Image"""
        if not self.current_img or not self.current_img.images:
            return None
        
        if sprite_index >= len(self.current_img.images):
            return None
        
        try:
            sprite = self.current_img.image_by_index(sprite_index)
            if not sprite.data:
                return None
            
            # RGBA 格式
            expected_size = sprite.w * sprite.h * 4
            if len(sprite.data) == expected_size:
                return Image.frombytes('RGBA', (sprite.w, sprite.h), sprite.data)
            
            # RGB 格式
            expected_size = sprite.w * sprite.h * 3
            if len(sprite.data) == expected_size:
                return Image.frombytes('RGB', (sprite.w, sprite.h), sprite.data)
            
            # 调色板模式
            expected_size = sprite.w * sprite.h
            if len(sprite.data) == expected_size:
                return self._convert_palette_image(sprite)
            
            return None
            
        except Exception as e:
            print(f"Error converting sprite to image: {e}")
            return None
    
    def get_current_pil_image(self) -> Optional[Image.Image]:
        """获取当前 Sprite 的 PIL Image"""
        return self.get_sprite_image(self.current_sprite_index)
    
    def _convert_palette_image(self, sprite) -> Optional[Image.Image]:
        """将调色板模式 Sprite 转换为 PIL Image"""
        if not hasattr(self.current_img, 'color_boards') or not self.current_img.color_boards:
            return None
        
        palette = self.current_img.color_boards[self.current_palette_index]
        img = Image.new('RGBA', (sprite.w, sprite.h))
        pixels = img.load()
        
        for y in range(sprite.h):
            for x in range(sprite.w):
                idx = sprite.data[y * sprite.w + x]
                if idx < len(palette.colors):
                    pixels[x, y] = palette.colors[idx]
                else:
                    pixels[x, y] = (0, 0, 0, 0)
        
        return img
    
    def get_palette_count(self) -> int:
        """获取当前 IMG 的调色板数量"""
        if not self.current_img or not hasattr(self.current_img, 'color_boards'):
            return 0
        return len(self.current_img.color_boards)
    
    def get_palette_info(self) -> List[dict]:
        """获取所有调色板的信息"""
        if not self.current_img or not hasattr(self.current_img, 'color_boards'):
            return []
        
        info_list = []
        for i, palette in enumerate(self.current_img.color_boards):
            info_list.append({
                'index': i,
                'colors': len(palette.colors)
            })
        return info_list
    
    def get_current_palette_colors(self) -> List[tuple]:
        """获取当前调色板的所有颜色"""
        if not self.current_img or not hasattr(self.current_img, 'color_boards'):
            return []
        
        if self.current_palette_index >= len(self.current_img.color_boards):
            return []
        
        return self.current_img.color_boards[self.current_palette_index].colors
    
    def set_palette(self, index: int) -> bool:
        """设置当前使用的调色板索引"""
        count = self.get_palette_count()
        if 0 <= index < count:
            self.current_palette_index = index
            return True
        return False
    
    def goto_sprite(self, index: int) -> bool:
        """跳转到指定 Sprite"""
        count = self.get_current_sprite_count()
        if 0 <= index < count:
            self.current_sprite_index = index
            return True
        return False


class NpkViewerApp:
    """NPK 浏览器应用程序"""
    
    def __init__(self, root: tk.Tk, initial_file: Optional[str] = None):
        self.root = root
        self.root.title("NPK Viewer - NPK 文件浏览器")
        self.root.geometry("1600x1000")
        self.root.minsize(1200, 800)
        
        self.loader = NpkImageLoader()
        self.current_photo: Optional[ImageTk.PhotoImage] = None
        self.bg_photo: Optional[ImageTk.PhotoImage] = None
        self.color_photos: List[ImageTk.PhotoImage] = []
        
        # 动画相关
        self.animation_running = False
        self.animation_after_id = None
        
        self._create_ui()
        self._bind_events()
        
        if initial_file and Path(initial_file).exists():
            self._load_npk_file(initial_file)
    
    def _create_ui(self):
        """创建用户界面 - 三栏布局"""
        # 主框架
        self.main_frame = ttk.Frame(self.root, padding="5")
        self.main_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)
        self.main_frame.columnconfigure(0, weight=0)  # 左栏固定宽度
        self.main_frame.columnconfigure(1, weight=0)  # 中栏固定宽度
        self.main_frame.columnconfigure(2, weight=1)  # 右栏自适应
        self.main_frame.rowconfigure(1, weight=1)
        
        # ===== 顶部工具栏 =====
        self._create_toolbar()
        
        # ===== 左栏：IMG 文件列表 =====
        self._create_left_panel()
        
        # ===== 中栏：帧列表 + 调色板 =====
        self._create_middle_panel()
        
        # ===== 右栏：图片预览 + 功能按钮 =====
        self._create_right_panel()
        
        # ===== 状态栏 =====
        self.status_bar = ttk.Label(self.main_frame, text="就绪", relief=tk.SUNKEN, anchor=tk.W)
        self.status_bar.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(5, 0))
    
    def _create_toolbar(self):
        """创建顶部工具栏"""
        self.toolbar = ttk.Frame(self.main_frame, padding="5")
        self.toolbar.grid(row=0, column=0, columnspan=3, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.open_btn = ttk.Button(self.toolbar, text="打开 NPK 文件", command=self._open_file)
        self.open_btn.pack(side=tk.LEFT, padx=(0, 10))
        
        self.export_btn = ttk.Button(self.toolbar, text="导出当前图片", command=self._export_image)
        self.export_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.export_btn.config(state=tk.DISABLED)
        
        self.export_all_btn = ttk.Button(self.toolbar, text="导出所有", command=self._export_all_images)
        self.export_all_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.export_all_btn.config(state=tk.DISABLED)
        
        self.info_label = ttk.Label(self.toolbar, text="请点击'打开 NPK 文件'开始")
        self.info_label.pack(side=tk.LEFT, padx=20)
    
    def _create_left_panel(self):
        """创建左栏 - IMG 文件列表"""
        self.left_frame = ttk.LabelFrame(self.main_frame, text="IMG 文件列表", padding="5", width=320)
        self.left_frame.grid(row=1, column=0, sticky=(tk.W, tk.N, tk.S), padx=(0, 5))
        self.left_frame.grid_propagate(False)  # 固定宽度，不随内容扩展
        self.left_frame.columnconfigure(0, weight=1)
        self.left_frame.rowconfigure(1, weight=1)  # 文件列表行可扩展
        
        # 搜索框
        search_frame = ttk.Frame(self.left_frame)
        search_frame.grid(row=0, column=0, sticky=(tk.W, tk.E), pady=(0, 5))
        
        self.search_var = tk.StringVar()
        self.search_entry = ttk.Entry(search_frame, textvariable=self.search_var)
        self.search_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=(0, 5))
        
        self.search_btn = ttk.Button(search_frame, text="搜索", command=self._search_files, width=6)
        self.search_btn.pack(side=tk.LEFT)
        
        # 文件列表 Treeview
        tree_frame = ttk.Frame(self.left_frame)
        tree_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        tree_frame.columnconfigure(0, weight=1)
        tree_frame.rowconfigure(0, weight=1)
        
        self.img_tree = ttk.Treeview(
            tree_frame,
            columns=('index', 'name', 'count'),
            show='headings',
            selectmode='browse'
        )
        self.img_tree.heading('index', text='#')
        self.img_tree.heading('name', text='IMG文件名')
        self.img_tree.heading('count', text='帧数')
        self.img_tree.column('index', width=40, anchor=tk.CENTER)
        self.img_tree.column('name', width=200)
        self.img_tree.column('count', width=50, anchor=tk.CENTER)
        
        vsb = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.img_tree.yview)
        hsb = ttk.Scrollbar(tree_frame, orient=tk.HORIZONTAL, command=self.img_tree.xview)
        self.img_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.img_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        vsb.grid(row=0, column=1, sticky=(tk.N, tk.S))
        hsb.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        # 绑定选择事件
        self.img_tree.bind('<<TreeviewSelect>>', self._on_img_select)
    
    def _create_middle_panel(self):
        """创建中栏 - 帧列表 + 调色板"""
        self.middle_frame = ttk.Frame(self.main_frame, width=360)
        self.middle_frame.grid(row=1, column=1, sticky=(tk.W, tk.N, tk.S), padx=(0, 5))
        self.middle_frame.grid_propagate(False)  # 固定宽度
        self.middle_frame.columnconfigure(0, weight=1)
        self.middle_frame.rowconfigure(0, weight=1)  # 帧列表可扩展
        self.middle_frame.rowconfigure(1, weight=0)  # 调色板区域固定高度
        
        # ===== 帧列表区域 =====
        self.frame_list_frame = ttk.LabelFrame(self.middle_frame, text="帧列表", padding="5")
        self.frame_list_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        self.frame_list_frame.columnconfigure(0, weight=1)
        self.frame_list_frame.rowconfigure(0, weight=1)
        
        # 帧列表 Treeview
        frame_tree_frame = ttk.Frame(self.frame_list_frame)
        frame_tree_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        frame_tree_frame.columnconfigure(0, weight=1)
        frame_tree_frame.rowconfigure(0, weight=1)
        
        self.frame_tree = ttk.Treeview(
            frame_tree_frame,
            columns=('index', 'format', 'pos', 'size'),
            show='headings',
            selectmode='browse'
        )
        self.frame_tree.heading('index', text='帧号')
        self.frame_tree.heading('format', text='颜色格式')
        self.frame_tree.heading('pos', text='基准坐标')
        self.frame_tree.heading('size', text='尺寸')
        self.frame_tree.column('index', width=50, anchor=tk.CENTER)
        self.frame_tree.column('format', width=80, anchor=tk.CENTER)
        self.frame_tree.column('pos', width=100, anchor=tk.CENTER)
        self.frame_tree.column('size', width=80, anchor=tk.CENTER)
        
        vsb = ttk.Scrollbar(frame_tree_frame, orient=tk.VERTICAL, command=self.frame_tree.yview)
        hsb = ttk.Scrollbar(frame_tree_frame, orient=tk.HORIZONTAL, command=self.frame_tree.xview)
        self.frame_tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        self.frame_tree.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        vsb.grid(row=0, column=1, sticky=(tk.N, tk.S))
        hsb.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        self.frame_tree.bind('<<TreeviewSelect>>', self._on_frame_select)
        
        # ===== 调色板区域 =====
        self.palette_frame = ttk.LabelFrame(self.middle_frame, text="调色板", padding="5")
        self.palette_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N), pady=(5, 0))
        self.palette_frame.columnconfigure(0, weight=1)
        
        # 当前选中颜色预览（大色块）
        self.selected_color_preview = tk.Canvas(self.palette_frame, width=60, height=60, bg='#808080', highlightthickness=1, highlightbackground='#999999')
        self.selected_color_preview.grid(row=0, column=0, pady=(0, 5))
        
        # 调色板 Canvas - 固定高度，只显示48个色块（12x4）
        self.palette_canvas = tk.Canvas(self.palette_frame, bg='#f5f5f5', highlightthickness=0, width=240, height=80)
        self.palette_canvas.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        # 颜色详情标签
        self.color_detail_label = ttk.Label(self.palette_frame, text="点击色块查看", font=('Microsoft YaHei', 9))
        self.color_detail_label.grid(row=2, column=0, sticky=(tk.W, tk.E), pady=(3, 0))
        
        # 调色板选择器 - 右下角
        palette_select_frame = ttk.Frame(self.palette_frame)
        palette_select_frame.grid(row=3, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
        self.palette_info_label = ttk.Label(palette_select_frame, text="0/1")
        self.palette_info_label.pack(side=tk.LEFT)
        
        ttk.Label(palette_select_frame, text=" 调色板:").pack(side=tk.LEFT)
        self.palette_var = tk.StringVar(value="0")
        self.palette_combo = ttk.Combobox(
            palette_select_frame,
            textvariable=self.palette_var,
            values=["0"],
            width=4,
            state='disabled'
        )
        self.palette_combo.pack(side=tk.LEFT, padx=5)
        self.palette_combo.bind('<<ComboboxSelected>>', self._on_palette_change)
    
    def _create_right_panel(self):
        """创建右栏 - 图片预览 + 功能按钮"""
        self.right_frame = ttk.Frame(self.main_frame)
        self.right_frame.grid(row=1, column=2, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.right_frame.columnconfigure(0, weight=1)
        self.right_frame.rowconfigure(0, weight=1)
        
        # ===== 图片预览区域 =====
        self.preview_frame = ttk.LabelFrame(self.right_frame, text="图片预览", padding="5")
        self.preview_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), pady=(0, 5))
        self.preview_frame.columnconfigure(0, weight=1)
        self.preview_frame.rowconfigure(0, weight=1)
        
        # 图片 Canvas
        canvas_frame = ttk.Frame(self.preview_frame)
        canvas_frame.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)
        
        self.preview_canvas = tk.Canvas(canvas_frame, bg='#808080', highlightthickness=0)
        self.preview_scroll_y = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=self.preview_canvas.yview)
        self.preview_scroll_x = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=self.preview_canvas.xview)
        self.preview_canvas.configure(yscrollcommand=self.preview_scroll_y.set, xscrollcommand=self.preview_scroll_x.set)
        
        self.preview_canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        self.preview_scroll_y.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.preview_scroll_x.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        # 图片信息
        self.image_info_label = ttk.Label(self.preview_frame, text="请选择 IMG 文件和帧查看")
        self.image_info_label.grid(row=1, column=0, sticky=(tk.W, tk.E), pady=(5, 0))
        
        # ===== 功能按钮区域 =====
        self.control_frame = ttk.LabelFrame(self.right_frame, text="功能控制", padding="5")
        self.control_frame.grid(row=1, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        
        # 缩放控制
        zoom_frame = ttk.Frame(self.control_frame)
        zoom_frame.pack(fill=tk.X, pady=2)
        
        ttk.Label(zoom_frame, text="缩放:").pack(side=tk.LEFT)
        self.scale_var = tk.DoubleVar(value=4.0)
        self.scale_combo = ttk.Combobox(
            zoom_frame,
            textvariable=self.scale_var,
            values=[0.25, 0.5, 0.75, 1.0, 1.5, 2.0, 3.0, 4.0, 8.0],
            width=5,
            state='readonly'
        )
        self.scale_combo.pack(side=tk.LEFT, padx=5)
        self.scale_combo.bind('<<ComboboxSelected>>', lambda e: self._update_preview())
        
        self.bg_btn = ttk.Button(zoom_frame, text="棋盘格背景", command=self._toggle_background, width=12)
        self.bg_btn.pack(side=tk.RIGHT)
        
        # 导航控制
        nav_frame = ttk.Frame(self.control_frame)
        nav_frame.pack(fill=tk.X, pady=2)
        
        self.prev_btn = ttk.Button(nav_frame, text="◀ 上一帧", command=self._prev_frame, width=10)
        self.prev_btn.pack(side=tk.LEFT, padx=(0, 5))
        self.prev_btn.config(state=tk.DISABLED)
        
        self.page_var = tk.StringVar(value="0 / 0")
        ttk.Label(nav_frame, textvariable=self.page_var, width=10).pack(side=tk.LEFT, padx=5)
        
        self.next_btn = ttk.Button(nav_frame, text="下一帧 ▶", command=self._next_frame, width=10)
        self.next_btn.pack(side=tk.LEFT, padx=5)
        self.next_btn.config(state=tk.DISABLED)
        
        self.goto_entry = ttk.Entry(nav_frame, width=6, justify=tk.CENTER)
        self.goto_entry.pack(side=tk.LEFT, padx=5)
        self.goto_entry.insert(0, "0")
        
        ttk.Button(nav_frame, text="跳转", command=self._goto_frame, width=6).pack(side=tk.LEFT)
        
        # 动画控制
        anim_frame = ttk.Frame(self.control_frame)
        anim_frame.pack(fill=tk.X, pady=2)
        
        self.play_btn = ttk.Button(anim_frame, text="▶ 播放动画", command=self._toggle_animation, width=12)
        self.play_btn.pack(side=tk.LEFT, padx=(0, 5))
        
        ttk.Label(anim_frame, text="间隔:").pack(side=tk.LEFT)
        self.anim_interval = tk.IntVar(value=100)
        ttk.Spinbox(anim_frame, from_=50, to=1000, increment=50, textvariable=self.anim_interval, width=6).pack(side=tk.LEFT, padx=5)
        ttk.Label(anim_frame, text="ms").pack(side=tk.LEFT)
        
        # 批量功能
        batch_frame = ttk.Frame(self.control_frame)
        batch_frame.pack(fill=tk.X, pady=2)
        
        ttk.Button(batch_frame, text="全帧展示", command=self._show_all_frames, width=12).pack(side=tk.LEFT, padx=(0, 5))
        ttk.Button(batch_frame, text="批量导出", command=self._batch_export, width=12).pack(side=tk.LEFT)
        
        self.checkerboard_bg = False
    
    def _bind_events(self):
        """绑定事件"""
        self.root.bind('<Left>', lambda e: self._prev_frame())
        self.root.bind('<Right>', lambda e: self._next_frame())
        self.search_entry.bind('<Return>', lambda e: self._search_files())
        self.goto_entry.bind('<Return>', lambda e: self._goto_frame())
        self.preview_canvas.bind('<MouseWheel>', self._on_preview_mousewheel)
    
    def _on_preview_mousewheel(self, event):
        """处理鼠标滚轮事件"""
        if event.delta > 0:
            self.preview_canvas.yview_scroll(-3, 'units')
        elif event.delta < 0:
            self.preview_canvas.yview_scroll(3, 'units')
    
    def _open_file(self):
        """打开 NPK 文件对话框"""
        file_path = filedialog.askopenfilename(
            title="选择 NPK 文件",
            filetypes=[("NPK 文件", "*.npk"), ("所有文件", "*.*")]
        )
        
        if file_path:
            self._load_npk_file(file_path)
    
    def _load_npk_file(self, file_path: str):
        """加载 NPK 文件"""
        if self.loader.load_npk(file_path):
            self._populate_img_list()
            self.info_label.config(text=f"已加载: {Path(file_path).name}")
            self.status_bar.config(text=f"文件: {file_path} | 共 {len(self.loader.npk.files)} 个 IMG 文件")
            self.export_btn.config(state=tk.NORMAL)
            self.export_all_btn.config(state=tk.NORMAL)
            
            # 清空其他列表
            for item in self.frame_tree.get_children():
                self.frame_tree.delete(item)
            self.palette_canvas.delete('all')
            self.preview_canvas.delete('all')
    
    def _populate_img_list(self):
        """填充 IMG 文件列表"""
        for item in self.img_tree.get_children():
            self.img_tree.delete(item)
        
        files = self.loader.get_file_list()
        for idx, name, count, version in files:
            self.img_tree.insert('', tk.END, values=(idx, name, count))
    
    def _on_img_select(self, event=None):
        """选择 IMG 文件时"""
        selection = self.img_tree.selection()
        if not selection:
            return
        
        item = self.img_tree.item(selection[0])
        index = int(item['values'][0])
        
        if self.loader.load_img_file(index):
            self._populate_frame_list()
            self._update_palette_display()
            self._update_preview()
            self._update_nav_buttons()
    
    def _populate_frame_list(self):
        """填充帧列表"""
        for item in self.frame_tree.get_children():
            self.frame_tree.delete(item)
        
        sprites = self.loader.get_sprite_list()
        for sprite in sprites:
            # 格式化颜色格式
            format_str = self._get_format_string(sprite['format'])
            pos_str = f"({sprite['x']}, {sprite['y']})"
            size_str = f"{sprite['width']}×{sprite['height']}"
            
            self.frame_tree.insert('', tk.END, values=(
                sprite['index'],
                format_str,
                pos_str,
                size_str
            ))
    
    def _get_format_string(self, fmt: int) -> str:
        """获取颜色格式的字符串表示"""
        format_map = {
            0: "1555",
            1: "4444",
            2: "8888",
            3: "Link",
            14: "索引",
            15: "DXT1",
            16: "DXT3",
            17: "DXT5",
        }
        return format_map.get(fmt, f"{fmt}")
    
    def _on_frame_select(self, event=None):
        """选择帧时"""
        selection = self.frame_tree.selection()
        if not selection:
            return
        
        item = self.frame_tree.item(selection[0])
        index = int(item['values'][0])
        
        self.loader.goto_sprite(index)
        self._update_preview()
        self._update_nav_buttons()
    
    def _update_palette_display(self):
        """更新调色板显示"""
        self.palette_canvas.delete('all')
        self.color_photos.clear()
        
        palette_count = self.loader.get_palette_count()
        
        if palette_count == 0:
            self.palette_combo.config(state='disabled')
            self.palette_info_label.config(text="(无调色板)")
            self.color_detail_label.config(text="此 IMG 不使用调色板")
            self.palette_frame.grid_remove()
            return
        
        self.palette_frame.grid()
        
        # 更新调色板选择器
        if palette_count > 1:
            self.palette_combo.config(state='readonly')
        else:
            self.palette_combo.config(state='disabled')
        
        self.palette_combo['values'] = [str(i) for i in range(palette_count)]
        self.palette_var.set(str(self.loader.current_palette_index))
        
        palette_info = self.loader.get_palette_info()
        if self.loader.current_palette_index < len(palette_info):
            colors = palette_info[self.loader.current_palette_index]['colors']
            self.palette_info_label.config(text=f"{self.loader.current_palette_index + 1}/{palette_count}")
        
        # 渲染颜色块
        self._render_palette_colors()
    
    def _render_palette_colors(self):
        """渲染调色板颜色块 - 最多48个（12x4）"""
        colors = self.loader.get_current_palette_colors()
        if not colors:
            return
        
        # 只取前48个颜色
        colors = colors[:48]
        
        # 设置颜色块参数 - 12x4 网格
        block_size = 18
        blocks_per_row = 12
        padding = 1
        
        # 计算需要的行数（最多4行）
        total_colors = len(colors)
        rows = min(4, (total_colors + blocks_per_row - 1) // blocks_per_row)
        
        # 设置 Canvas 固定大小
        canvas_width = 12 * (block_size + padding) + padding  # 240px
        canvas_height = 4 * (block_size + padding) + padding  # 80px
        self.palette_canvas.config(width=canvas_width, height=canvas_height)
        
        # 绘制颜色块
        for i, color in enumerate(colors):
            row = i // blocks_per_row
            col = i % blocks_per_row
            
            x1 = padding + col * (block_size + padding)
            y1 = padding + row * (block_size + padding)
            x2 = x1 + block_size
            y2 = y1 + block_size
            
            r, g, b, a = color
            hex_color = f'#{r:02x}{g:02x}{b:02x}'
            
            # 处理透明色
            if a < 128:
                # 绘制棋盘格背景表示透明
                self._draw_transparent_bg(self.palette_canvas, x1, y1, x2, y2)
            
            rect_id = self.palette_canvas.create_rectangle(
                x1, y1, x2, y2,
                fill=hex_color,
                outline='#999999',
                tags=f'color_{i}'
            )
            
            # 绑定点击事件
            self.palette_canvas.tag_bind(
                rect_id, '<Button-1>',
                lambda e, idx=i, c=color: self._on_color_click(idx, c)
            )
        
        # 初始化选中第一个颜色
        if colors:
            self._on_color_click(0, colors[0])
    
    def _draw_transparent_bg(self, canvas, x1, y1, x2, y2):
        """绘制透明背景"""
        cell_size = 4
        for y in range(int(y1), int(y2), cell_size):
            for x in range(int(x1), int(x2), cell_size):
                color = '#ffffff' if ((x // cell_size) + (y // cell_size)) % 2 == 0 else '#cccccc'
                canvas.create_rectangle(
                    x, y, min(x + cell_size, x2), min(y + cell_size, y2),
                    fill=color, outline=''
                )
    
    def _on_color_click(self, index: int, color: tuple):
        """颜色块点击事件"""
        r, g, b, a = color
        hex_color = f'#{r:02x}{g:02x}{b:02x}'
        
        # 更新上方预览色块
        self.selected_color_preview.config(bg=hex_color)
        
        # 更新详情标签
        self.color_detail_label.config(
            text=f"#{index} {hex_color}"
        )
    
    def _on_palette_change(self, event=None):
        """调色板改变时"""
        try:
            palette_index = int(self.palette_var.get())
            if self.loader.set_palette(palette_index):
                # 更新调色板信息标签
                palette_count = self.loader.get_palette_count()
                self.palette_info_label.config(text=f"{palette_index + 1}/{palette_count}")
                self._update_palette_display()
                self._update_preview()
        except ValueError:
            pass
    
    def _update_preview(self):
        """更新图片预览 - 居中显示"""
        pil_img = self.loader.get_current_pil_image()
        
        # 获取 Canvas 当前大小
        canvas_width = self.preview_canvas.winfo_width()
        canvas_height = self.preview_canvas.winfo_height()
        
        if pil_img is None:
            self.preview_canvas.delete('all')
            self.preview_canvas.create_text(
                canvas_width // 2,
                canvas_height // 2,
                text="无法显示此图像",
                fill='white',
                font=('Microsoft YaHei', 12)
            )
            self.image_info_label.config(text="无法显示图像")
            self.page_var.set("0 / 0")
            return
        
        # 缩放
        scale = self.scale_var.get()
        if scale != 1.0:
            new_size = (int(pil_img.width * scale), int(pil_img.height * scale))
            display_img = pil_img.resize(new_size, Image.Resampling.NEAREST)
        else:
            display_img = pil_img
        
        self.current_photo = ImageTk.PhotoImage(display_img)
        
        self.preview_canvas.delete('all')
        
        # 计算居中位置
        img_width = self.current_photo.width()
        img_height = self.current_photo.height()
        
        # 确保 Canvas 有足够滚动区域，图片居中
        scroll_width = max(canvas_width, img_width)
        scroll_height = max(canvas_height, img_height)
        
        offset_x = (scroll_width - img_width) // 2
        offset_y = (scroll_height - img_height) // 2
        
        self.preview_canvas.config(scrollregion=(0, 0, scroll_width, scroll_height))
        
        # 棋盘格背景（覆盖整个滚动区域）
        if self.checkerboard_bg:
            bg_img = self._create_checkerboard(scroll_width, scroll_height)
            self.bg_photo = ImageTk.PhotoImage(bg_img)
            self.preview_canvas.create_image(0, 0, anchor=tk.NW, image=self.bg_photo)
        else:
            # 填充灰色背景
            self.preview_canvas.create_rectangle(
                0, 0, scroll_width, scroll_height,
                fill='#808080', outline=''
            )
        
        # 居中显示图片
        self.preview_canvas.create_image(offset_x, offset_y, anchor=tk.NW, image=self.current_photo)
        
        # 滚动到中心位置
        if scroll_width > canvas_width:
            self.preview_canvas.xview_moveto((offset_x - (canvas_width - img_width) // 2) / scroll_width)
        if scroll_height > canvas_height:
            self.preview_canvas.yview_moveto((offset_y - (canvas_height - img_height) // 2) / scroll_height)
        
        # 更新信息
        info = self.loader.get_current_sprite_info()
        if info:
            self.image_info_label.config(
                text=f"帧 {info['index']+1}/{info['count']} | 尺寸: {info['width']}×{info['height']} | "
                     f"格式: {self._get_format_string(info['format'])} | 坐标: ({info['x']}, {info['y']})"
            )
            self.page_var.set(f"{info['index'] + 1} / {info['count']}")
            self.goto_entry.delete(0, tk.END)
            self.goto_entry.insert(0, str(info['index'] + 1))
    
    def _create_checkerboard(self, width: int, height: int) -> Image.Image:
        """创建棋盘格背景"""
        cell_size = 16
        img = Image.new('RGB', (width, height), (255, 255, 255))
        draw = ImageDraw.Draw(img)
        
        color1 = (255, 255, 255)
        color2 = (200, 200, 200)
        
        for y in range(0, height, cell_size):
            for x in range(0, width, cell_size):
                color = color1 if ((x // cell_size) + (y // cell_size)) % 2 == 0 else color2
                draw.rectangle(
                    [x, y, min(x + cell_size, width), min(y + cell_size, height)],
                    fill=color
                )
        
        return img
    
    def _update_nav_buttons(self):
        """更新导航按钮状态"""
        info = self.loader.get_current_sprite_info()
        if not info:
            self.prev_btn.config(state=tk.DISABLED)
            self.next_btn.config(state=tk.DISABLED)
            return
        
        count = info['count']
        index = info['index']
        
        self.prev_btn.config(state=tk.NORMAL if index > 0 else tk.DISABLED)
        self.next_btn.config(state=tk.NORMAL if index < count - 1 else tk.DISABLED)
    
    def _prev_frame(self):
        """上一帧"""
        if self.loader.current_sprite_index > 0:
            self.loader.current_sprite_index -= 1
            self._select_frame_in_tree(self.loader.current_sprite_index)
            self._update_preview()
            self._update_nav_buttons()
    
    def _next_frame(self):
        """下一帧"""
        count = self.loader.get_current_sprite_count()
        if self.loader.current_sprite_index < count - 1:
            self.loader.current_sprite_index += 1
            self._select_frame_in_tree(self.loader.current_sprite_index)
            self._update_preview()
            self._update_nav_buttons()
    
    def _goto_frame(self):
        """跳转到指定帧"""
        try:
            index = int(self.goto_entry.get()) - 1
            if self.loader.goto_sprite(index):
                self._select_frame_in_tree(index)
                self._update_preview()
                self._update_nav_buttons()
        except ValueError:
            pass
    
    def _select_frame_in_tree(self, index: int):
        """在帧列表中选中指定索引"""
        children = self.frame_tree.get_children()
        if 0 <= index < len(children):
            self.frame_tree.selection_set(children[index])
            self.frame_tree.see(children[index])
    
    def _toggle_background(self):
        """切换棋盘格背景"""
        self.checkerboard_bg = not self.checkerboard_bg
        self.bg_btn.config(text="棋盘格关" if self.checkerboard_bg else "棋盘格开")
        self._update_preview()
    
    def _toggle_animation(self):
        """切换动画播放状态"""
        if self.animation_running:
            self._stop_animation()
        else:
            self._start_animation()
    
    def _start_animation(self):
        """开始播放动画"""
        count = self.loader.get_current_sprite_count()
        if count <= 1:
            messagebox.showinfo("提示", "当前 IMG 只有一帧，无法播放动画")
            return
        
        self.animation_running = True
        self.play_btn.config(text="⏸ 停止播放")
        self._animate_frame()
    
    def _stop_animation(self):
        """停止播放动画"""
        self.animation_running = False
        self.play_btn.config(text="▶ 播放动画")
        if self.animation_after_id:
            self.root.after_cancel(self.animation_after_id)
            self.animation_after_id = None
    
    def _animate_frame(self):
        """动画帧"""
        if not self.animation_running:
            return
        
        count = self.loader.get_current_sprite_count()
        next_index = (self.loader.current_sprite_index + 1) % count
        
        self.loader.goto_sprite(next_index)
        self._select_frame_in_tree(next_index)
        self._update_preview()
        self._update_nav_buttons()
        
        interval = self.anim_interval.get()
        self.animation_after_id = self.root.after(interval, self._animate_frame)
    
    def _show_all_frames(self):
        """全帧展示 - 在新窗口中显示所有帧"""
        count = self.loader.get_current_sprite_count()
        if count == 0:
            messagebox.showinfo("提示", "当前 IMG 没有帧")
            return
        
        # 创建新窗口
        all_window = tk.Toplevel(self.root)
        all_window.title(f"全帧展示 - {self.loader.current_img_file.name}")
        all_window.geometry("1200x800")
        
        # 创建 Canvas 和滚动条
        canvas_frame = ttk.Frame(all_window, padding="10")
        canvas_frame.pack(fill=tk.BOTH, expand=True)
        
        canvas = tk.Canvas(canvas_frame, bg='#808080')
        vsb = ttk.Scrollbar(canvas_frame, orient=tk.VERTICAL, command=canvas.yview)
        hsb = ttk.Scrollbar(canvas_frame, orient=tk.HORIZONTAL, command=canvas.xview)
        canvas.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        
        canvas.grid(row=0, column=0, sticky=(tk.W, tk.E, tk.N, tk.S))
        vsb.grid(row=0, column=1, sticky=(tk.N, tk.S))
        hsb.grid(row=1, column=0, sticky=(tk.W, tk.E))
        
        canvas_frame.columnconfigure(0, weight=1)
        canvas_frame.rowconfigure(0, weight=1)
        
        # 加载所有帧
        photos = []
        x_offset = 10
        y_offset = 10
        row_height = 0
        
        for i in range(count):
            pil_img = self.loader.get_sprite_image(i)
            if pil_img:
                # 缩放以便查看
                max_size = 128
                if pil_img.width > max_size or pil_img.height > max_size:
                    ratio = min(max_size / pil_img.width, max_size / pil_img.height)
                    new_size = (int(pil_img.width * ratio), int(pil_img.height * ratio))
                    pil_img = pil_img.resize(new_size, Image.Resampling.NEAREST)
                
                photo = ImageTk.PhotoImage(pil_img)
                photos.append(photo)
                
                # 绘制
                canvas.create_image(x_offset, y_offset, anchor=tk.NW, image=photo)
                canvas.create_text(x_offset + pil_img.width // 2, y_offset + pil_img.height + 10,
                                   text=f"#{i}", fill='white', font=('Microsoft YaHei', 9))
                
                x_offset += max(pil_img.width, 100) + 20
                row_height = max(row_height, pil_img.height + 40)
                
                # 换行
                if x_offset > 1000:
                    x_offset = 10
                    y_offset += row_height
                    row_height = 0
        
        # 更新滚动区域
        canvas.config(scrollregion=canvas.bbox('all'))
        
        # 保持引用
        all_window.photos = photos
    
    def _search_files(self):
        """搜索 IMG 文件"""
        keyword = self.search_var.get().lower()
        if not keyword:
            return
        
        children = self.img_tree.get_children()
        selection = self.img_tree.selection()
        start_index = 0
        
        if selection:
            try:
                start_index = children.index(selection[0]) + 1
            except ValueError:
                pass
        
        for i in range(start_index, len(children)):
            item = self.img_tree.item(children[i])
            name = str(item['values'][1]).lower()
            if keyword in name:
                self.img_tree.selection_set(children[i])
                self.img_tree.see(children[i])
                return
        
        for i in range(0, start_index):
            item = self.img_tree.item(children[i])
            name = str(item['values'][1]).lower()
            if keyword in name:
                self.img_tree.selection_set(children[i])
                self.img_tree.see(children[i])
                return
        
        messagebox.showinfo("搜索", f"未找到包含 '{keyword}' 的文件")
    
    def _export_image(self):
        """导出当前图片"""
        pil_img = self.loader.get_current_pil_image()
        if pil_img is None:
            messagebox.showerror("错误", "没有可导出的图像")
            return
        
        info = self.loader.get_current_sprite_info()
        if info:
            default_name = f"{self.loader.current_img_file.name.replace('/', '_').replace('\\', '_').replace('.img', '')}_frame{info['index']:04d}.png"
        else:
            default_name = "image.png"
        
        file_path = filedialog.asksaveasfilename(
            title="导出图片",
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[
                ("PNG 图片", "*.png"),
                ("JPEG 图片", "*.jpg;*.jpeg"),
                ("BMP 图片", "*.bmp"),
                ("所有文件", "*.*")
            ]
        )
        
        if file_path:
            try:
                ext = Path(file_path).suffix.lower()
                if ext in ['.jpg', '.jpeg'] and pil_img.mode == 'RGBA':
                    bg = Image.new('RGB', pil_img.size, (255, 255, 255))
                    bg.paste(pil_img, mask=pil_img.split()[3])
                    pil_img = bg
                
                pil_img.save(file_path)
                self.status_bar.config(text=f"已导出: {file_path}")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败:\n{e}")
    
    def _export_all_images(self):
        """导出当前 IMG 的所有图片"""
        if not self.loader.current_img:
            messagebox.showerror("错误", "请先选择一个 IMG 文件")
            return
        
        dir_path = filedialog.askdirectory(title="选择导出目录")
        if not dir_path:
            return
        
        count = self.loader.get_current_sprite_count()
        if count == 0:
            messagebox.showerror("错误", "当前 IMG 文件中没有图片")
            return
        
        self._do_export(dir_path, count)
    
    def _batch_export(self):
        """批量导出所有 IMG 的所有图片"""
        if not self.loader.npk:
            messagebox.showerror("错误", "请先打开 NPK 文件")
            return
        
        dir_path = filedialog.askdirectory(title="选择导出目录")
        if not dir_path:
            return
        
        total = 0
        for npk_file in self.loader.npk.files:
            try:
                img = npk_file.to_img()
                if img.images:
                    total += len(img.images)
            except:
                pass
        
        if total == 0:
            messagebox.showerror("错误", "NPK 文件中没有可导出的图片")
            return
        
        if not messagebox.askyesno("确认", f"将导出共 {total} 张图片。\n继续?"):
            return
        
        # 简单的批量导出
        exported = 0
        failed = 0
        
        for npk_file in self.loader.npk.files:
            try:
                img = npk_file.to_img()
                if not img.images:
                    continue
                
                file_prefix = npk_file.name.replace('/', '_').replace('\\', '_').replace('.img', '')
                
                for i in range(len(img.images)):
                    try:
                        sprite = img.image_by_index(i)
                        pil_img = self._convert_sprite_to_image(sprite, img)
                        
                        if pil_img:
                            file_name = f"{file_prefix}_{i:04d}.png"
                            file_path = os.path.join(dir_path, file_name)
                            pil_img.save(file_path)
                            exported += 1
                    except:
                        failed += 1
            except:
                pass
            
            self.status_bar.config(text=f"导出中... {exported} / {total}")
            self.root.update()
        
        messagebox.showinfo("完成", f"导出完成!\n成功: {exported}\n失败: {failed}")
        self.status_bar.config(text=f"导出完成: {exported} 成功, {failed} 失败")
    
    def _do_export(self, dir_path: str, count: int):
        """执行导出操作"""
        progress_win = tk.Toplevel(self.root)
        progress_win.title("导出进度")
        progress_win.geometry("400x120")
        progress_win.transient(self.root)
        progress_win.grab_set()
        
        ttk.Label(progress_win, text=f"正在导出 {count} 张图片...").pack(pady=10)
        progress = ttk.Progressbar(progress_win, maximum=count, mode='determinate')
        progress.pack(fill=tk.X, padx=20, pady=5)
        status_label = ttk.Label(progress_win, text="0 / 0")
        status_label.pack(pady=5)
        
        file_prefix = self.loader.current_img_file.name.replace('/', '_').replace('\\', '_').replace('.img', '')
        exported = 0
        failed = 0
        
        try:
            for i in range(count):
                pil_img = self.loader.get_sprite_image(i)
                
                if pil_img:
                    file_name = f"{file_prefix}_{i:04d}.png"
                    file_path = os.path.join(dir_path, file_name)
                    pil_img.save(file_path)
                    exported += 1
                else:
                    failed += 1
                
                progress['value'] = i + 1
                status_label.config(text=f"{i + 1} / {count}")
                progress_win.update()
        
        finally:
            progress_win.destroy()
            self._update_preview()
        
        messagebox.showinfo("完成", f"导出完成!\n成功: {exported}\n失败: {failed}")
    
    def _convert_sprite_to_image(self, sprite, img) -> Optional[Image.Image]:
        """将 Sprite 转换为 PIL Image（用于批量导出）"""
        try:
            if not sprite.data:
                return None
            
            expected_size = sprite.w * sprite.h * 4
            if len(sprite.data) == expected_size:
                return Image.frombytes('RGBA', (sprite.w, sprite.h), sprite.data)
            
            expected_size = sprite.w * sprite.h * 3
            if len(sprite.data) == expected_size:
                return Image.frombytes('RGB', (sprite.w, sprite.h), sprite.data)
            
            expected_size = sprite.w * sprite.h
            if len(sprite.data) == expected_size:
                if hasattr(img, 'color_boards') and img.color_boards:
                    palette = img.color_boards[0]
                    pil_img = Image.new('RGBA', (sprite.w, sprite.h))
                    pixels = pil_img.load()
                    
                    for y in range(sprite.h):
                        for x in range(sprite.w):
                            idx = sprite.data[y * sprite.w + x]
                            if idx < len(palette.colors):
                                pixels[x, y] = palette.colors[idx]
                            else:
                                pixels[x, y] = (0, 0, 0, 0)
                    
                    return pil_img
            
            return None
        except:
            return None


def main():
    """主入口"""
    initial_file = sys.argv[1] if len(sys.argv) > 1 else None
    
    root = tk.Tk()
    app = NpkViewerApp(root, initial_file)
    root.mainloop()


if __name__ == "__main__":
    main()
