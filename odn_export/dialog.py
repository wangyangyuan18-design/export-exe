# -*- coding: utf-8 -*-
"""Select a KMZ/KML source file and export ODN Excel."""
import os

from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (
    QDialog, QVBoxLayout, QHBoxLayout, QLabel, QPushButton, QFileDialog,
    QMessageBox, QDoubleSpinBox, QLineEdit, QPlainTextEdit, QProgressDialog,
    QGroupBox, QFormLayout
)

from .kml_source import load_kml_source, summarize_source
from .exporter import export_from_kml_file


_CATEGORY_LABELS = [
    ('Pole features（杆子）', 'pole'),
    ('HUB BOX points', 'hub_box'),
    ('SUB BOX points', 'sub_box'),
    ('SUB BOX Boundary polygons', 'subbox_boundary'),
    ('Distribution Cable lines', 'distribution_cable'),
    ('Home Passed points（实际存在类别）', 'home_passed'),
]


class ODNExportDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.source_data = None
        self.setWindowTitle('ODN Export Information - KMZ / KML')
        self.resize(760, 650)
        self._build()

    def _build(self):
        root = QVBoxLayout(self)
        intro = QLabel(
            '直接选择最终 KMZ / KML 作为数据源，不读取当前 QGIS 工程中的图层。\n'
            '无论当前打开哪个 QGIS 工程，插件只使用这里选择的源文件。文件夹/图层名称末尾的 =数量 会自动忽略。'
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        source_box = QGroupBox('1. 选择源 KMZ / KML 文件')
        source_layout = QVBoxLayout(source_box)
        source_row = QHBoxLayout()
        self.source = QLineEdit()
        self.source.setPlaceholderText('选择最终 KMZ 或 KML 文件')
        source_row.addWidget(self.source, 1)
        source_browse = QPushButton('选择文件...')
        source_browse.clicked.connect(self._browse_source)
        source_row.addWidget(source_browse)
        source_layout.addLayout(source_row)
        scan_row = QHBoxLayout()
        scan_row.addStretch(1)
        scan_button = QPushButton('扫描所选源文件')
        scan_button.clicked.connect(self.refresh_scan)
        scan_row.addWidget(scan_button)
        source_layout.addLayout(scan_row)
        root.addWidget(source_box)

        scan_box = QGroupBox('2. 源文件结构识别结果（按实际要素数量）')
        scan_layout = QVBoxLayout(scan_box)
        self.scan_text = QPlainTextEdit()
        self.scan_text.setReadOnly(True)
        self.scan_text.setMinimumHeight(300)
        scan_layout.addWidget(self.scan_text)
        root.addWidget(scan_box, 1)

        settings = QGroupBox('3. 导出设置')
        form = QFormLayout(settings)
        self.radius = QDoubleSpinBox()
        self.radius.setRange(0.1, 100.0)
        self.radius.setDecimals(1)
        self.radius.setSingleStep(0.5)
        self.radius.setValue(8.0)
        self.radius.setSuffix(' m')
        self.output = QLineEdit()
        self.output.setPlaceholderText('选择 Excel 保存路径')
        browse_row = QHBoxLayout()
        browse_row.addWidget(self.output, 1)
        output_browse = QPushButton('浏览...')
        output_browse.clicked.connect(self._browse_output)
        browse_row.addWidget(output_browse)
        form.addRow('杆子匹配半径（可修改）:', self.radius)
        form.addRow('Excel 文件:', browse_row)
        root.addWidget(settings)

        self.note = QLabel(
            '规则：SUB BOX 全量读取；每条 DC 按线名中最后一个 SUB BOX 端点归属；'
            'HPs 按同一 HUB 的 SUB BOX Boundary 统计，六类 Home Passed 有几类就统计几类。'
        )
        self.note.setWordWrap(True)
        self.note.setStyleSheet('color:#555;')
        root.addWidget(self.note)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.export_btn = QPushButton('导出 Excel')
        self.export_btn.setDefault(True)
        self.export_btn.setEnabled(False)
        self.export_btn.clicked.connect(self._export)
        close = QPushButton('关闭')
        close.clicked.connect(self.close)
        buttons.addWidget(self.export_btn)
        buttons.addWidget(close)
        root.addLayout(buttons)

    def _browse_source(self):
        path, _ = QFileDialog.getOpenFileName(
            self, '选择源 KMZ / KML 文件', self.source.text(),
            'KMZ / KML Files (*.kmz *.kml);;KMZ Files (*.kmz);;KML Files (*.kml)'
        )
        if path:
            self.source.setText(path)
            self.refresh_scan()

    def _browse_output(self):
        path, _ = QFileDialog.getSaveFileName(
            self, '保存 ODN Excel',
            self.output.text() or 'ODN_Export_Information.xlsx',
            'Excel Workbook (*.xlsx)'
        )
        if path:
            if not path.lower().endswith('.xlsx'):
                path += '.xlsx'
            self.output.setText(path)

    def refresh_scan(self):
        path = self.source.text().strip()
        self.source_data = None
        self.export_btn.setEnabled(False)
        if not path:
            self.scan_text.setPlainText('请先选择一个 KMZ / KML 源文件。')
            return
        try:
            self.source_data = load_kml_source(path)
            counts = summarize_source(self.source_data)
            lines = [
                '源文件：{}'.format(os.path.basename(path)),
                'KML 文档：{}'.format(self.source_data.get('kml_entry', '')),
                '',
                '实际要素读取数量：'
            ]
            for title, key in _CATEGORY_LABELS:
                lines.append('  {}：{}'.format(title, counts[key]))

            lines.append('')
            lines.append('各 HUB 分布（SUB BOX / Boundary / DC / HP 点要素）：')
            hubs = sorted({record.get('hub') for key in counts for record in self.source_data.get(key, [])
                           if record.get('hub')})
            for hub in hubs:
                def count(key):
                    return sum(1 for record in self.source_data.get(key, []) if record.get('hub') == hub)
                hp_types = sorted({record.get('layer', '') for record in self.source_data.get('home_passed', [])
                                   if record.get('hub') == hub})
                lines.append('  {}：SUB BOX {} / Boundary {} / DC {} / HP {} 点（类别：{}）'.format(
                    hub, count('sub_box'), count('subbox_boundary'), count('distribution_cable'),
                    count('home_passed'), ', '.join(hp_types) if hp_types else '无'
                ))

            if self.source_data.get('source_qa'):
                lines.append('')
                lines.append('源文件几何警告：{}'.format(len(self.source_data['source_qa'])))
                for item in self.source_data['source_qa'][:20]:
                    lines.append('  [{}] {} | {} | {}'.format(item[0], item[1], item[2], item[3]))

            self.scan_text.setPlainText('\n'.join(lines))
            self.export_btn.setEnabled(bool(self.source_data.get('sub_box')))
            if self.source_data.get('sub_box'):
                self.note.setText(
                    '已从源文件直接识别 {} 个 SUB BOX。DC 按最后一个 SUB BOX 端点归属；'
                    'HP 按同 HUB 的 Boundary 汇总，缺少某些 Home Passed 类别不会阻止统计。'.format(
                        len(self.source_data['sub_box'])
                    )
                )
            else:
                self.note.setText('没有识别到 SUB BOX 点要素，不能导出。请检查源文件文件夹结构。')
        except Exception as exc:
            self.source_data = None
            self.scan_text.setPlainText('源文件扫描失败：\n{}'.format(exc))
            self.note.setText('请检查源文件是否为有效 KMZ / KML。')

    def _export(self):
        source_path = self.source.text().strip()
        cached_path = self.source_data.get('source_path') if self.source_data else None
        if (not source_path or not self.source_data
                or os.path.abspath(source_path) != os.path.abspath(cached_path or '')):
            self.refresh_scan()
            if not self.source_data:
                return
        output_path = self.output.text().strip()
        if not output_path:
            self._browse_output()
            output_path = self.output.text().strip()
        if not output_path:
            return
        if not output_path.lower().endswith('.xlsx'):
            output_path += '.xlsx'
            self.output.setText(output_path)

        progress = QProgressDialog('正在从所选 KMZ / KML 读取并统计...', '取消', 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        self.export_btn.setEnabled(False)
        try:
            result = export_from_kml_file(
                source_path, output_path,
                pole_radius_m=float(self.radius.value()),
                progress=progress,
                source_data=self.source_data
            )
            progress.close()
            if result.get('cancelled'):
                QMessageBox.information(self, '已取消', '导出操作已取消。')
                return
            message = (
                '导出完成。\n\n'
                '源文件 SUB BOX：{rows}\n'
                'Distribution Cable 匹配：{cable_matched}/{cable_total}\n'
                'HP 汇总成功（含 0）：{hp_matched}/{rows}\n'
                '杆子匹配成功：{matched}/{total}\n'
                '未匹配杆子：{missing_poles}\n'
                '未找到 SUB BOX Boundary：{missing_boundaries}\n'
                'QA 检查项：{qa_count}\n\n'
                '文件：{path}\n'
                '第二个工作表为 QA Report。'
            ).format(**result)
            QMessageBox.information(self, 'ODN Export', message)
        except Exception as exc:
            progress.close()
            QMessageBox.critical(self, '导出失败', str(exc))
        finally:
            self.export_btn.setEnabled(bool(self.source_data and self.source_data.get('sub_box')))