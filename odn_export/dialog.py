# -*- coding: utf-8 -*-
"""Minimal UI for scanning loaded KMZ layers and exporting ODN Excel."""
import os
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import (QDialog, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QFileDialog, QMessageBox, QDoubleSpinBox, QLineEdit,
    QPlainTextEdit, QProgressDialog, QGroupBox, QFormLayout)
from qgis.core import QgsProject
from .kmz_tree import scan_project
from .exporter import export_from_kmz_project

class ODNExportDialog(QDialog):
    def __init__(self, iface, parent=None):
        super().__init__(parent or iface.mainWindow())
        self.iface = iface
        self.setWindowTitle('ODN Export Information - KMZ')
        self.resize(720, 600)
        self._build()
        self.refresh_scan()

    def _build(self):
        root = QVBoxLayout(self)
        intro = QLabel(
            '读取当前 QGIS 工程中已加载的 KMZ 图层组。图层/文件夹名称末尾的 =数量 会自动忽略。\\n'
            'HPs 根据同名 SUB BOX Boundary 内的 6 个 Home Passed 图层统计；杆子默认按 8 米最近距离匹配。'
        )
        intro.setWordWrap(True)
        root.addWidget(intro)

        scan_box = QGroupBox('1. KMZ 图层结构识别结果')
        scan_layout = QVBoxLayout(scan_box)
        self.scan_text = QPlainTextEdit()
        self.scan_text.setReadOnly(True)
        self.scan_text.setMinimumHeight(300)
        scan_layout.addWidget(self.scan_text)
        row = QHBoxLayout()
        refresh = QPushButton('重新扫描当前工程')
        refresh.clicked.connect(self.refresh_scan)
        row.addWidget(refresh)
        row.addStretch(1)
        scan_layout.addLayout(row)
        root.addWidget(scan_box, 1)

        settings = QGroupBox('2. 导出设置')
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
        browse = QPushButton('浏览...')
        browse.clicked.connect(self._browse)
        browse_row.addWidget(browse)
        form.addRow('杆子匹配半径（可修改）:', self.radius)
        form.addRow('Excel 文件:', browse_row)
        root.addWidget(settings)

        self.note = QLabel(
            'SPAN：KMZ 不含原始 Span 字段，程序优先按光缆线上可识别的杆子区间推算；无法识别时按折线顶点段数推算，均会写入 QA Report。'
        )
        self.note.setWordWrap(True)
        self.note.setStyleSheet('color:#555;')
        root.addWidget(self.note)

        buttons = QHBoxLayout()
        buttons.addStretch(1)
        self.export_btn = QPushButton('导出 Excel')
        self.export_btn.setDefault(True)
        self.export_btn.clicked.connect(self._export)
        close = QPushButton('关闭')
        close.clicked.connect(self.close)
        buttons.addWidget(self.export_btn)
        buttons.addWidget(close)
        root.addLayout(buttons)

    def refresh_scan(self):
        try:
            found = scan_project(QgsProject.instance())
            labels = [
                ('Pole layers（杆子）', 'pole'),
                ('HUB BOX layers', 'hub_box'),
                ('SUB BOX point layers', 'sub_box'),
                ('SUB BOX Boundary layers', 'subbox_boundary'),
                ('Distribution Cable layers', 'distribution_cable'),
                ('Home Passed layers（6类）', 'home_passed'),
            ]
            lines = ['识别统计（图层数）：']
            for title, key in labels:
                lines.append('  {}：{}'.format(title, len(found[key])))
            lines.append('')
            for title, key in labels:
                lines.append('[{}]'.format(title))
                if not found[key]:
                    lines.append('  未识别到')
                for rec in found[key]:
                    path = ' / '.join(list(rec['path']) + [rec['layer_name']])
                    lines.append('  ' + path)
            self.scan_text.setPlainText('\\n'.join(lines))
            required = all(found[key] for key in ('pole', 'sub_box', 'subbox_boundary', 'home_passed'))
            self.export_btn.setEnabled(required)
            if not required:
                self.note.setText('当前工程未识别到全部必要图层。请确认 KMZ 已完整加载，且图层组/名称与设计结构一致；扫描清单可用于定位缺失图层。')
            else:
                self.note.setText('SPAN：KMZ 不含原始 Span 字段，程序优先按光缆线上可识别的杆子区间推算；无法识别时按折线顶点段数推算，均会写入 QA Report。')
        except Exception as exc:
            self.scan_text.setPlainText('扫描失败：\\n{}'.format(exc))
            self.export_btn.setEnabled(False)

    def _browse(self):
        path, _ = QFileDialog.getSaveFileName(self, '保存 ODN Excel',
            self.output.text() or 'ODN_Export_Information.xlsx', 'Excel Workbook (*.xlsx)')
        if path:
            if not path.lower().endswith('.xlsx'):
                path += '.xlsx'
            self.output.setText(path)

    def _export(self):
        path = self.output.text().strip()
        if not path:
            self._browse()
            path = self.output.text().strip()
        if not path:
            return
        if not path.lower().endswith('.xlsx'):
            path += '.xlsx'
            self.output.setText(path)
        progress = QProgressDialog('正在读取 KMZ 图层并统计 HP...', '取消', 0, 100, self)
        progress.setWindowModality(Qt.WindowModal)
        progress.setMinimumDuration(0)
        progress.show()
        self.export_btn.setEnabled(False)
        try:
            result = export_from_kmz_project(QgsProject.instance(), path,
                pole_radius_m=float(self.radius.value()), progress=progress)
            progress.close()
            if result.get('cancelled'):
                QMessageBox.information(self, '已取消', '导出操作已取消。')
                return
            message = ('导出完成。\\n\\n'
                'SUB BOX 记录：{rows}\\n'
                '杆子匹配成功：{matched}/{total}\\n'
                '未匹配杆子：{missing_poles}\\n'
                '未找到 SUB BOX Boundary：{missing_boundaries}\\n'
                'QA 检查项：{qa_count}\\n\\n'
                '文件：{path}\\n'
                '第二个工作表为 QA Report。').format(**result)
            QMessageBox.information(self, 'ODN Export', message)
        except Exception as exc:
            progress.close()
            QMessageBox.critical(self, '导出失败', str(exc))
        finally:
            self.export_btn.setEnabled(True)
            self.refresh_scan()
