# -*- coding: utf-8 -*-
import os
from qgis.PyQt.QtWidgets import QAction, QMessageBox
from qgis.PyQt.QtGui import QIcon


class ODNExportPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.action = None
        self.dialog = None

    def initGui(self):
        icon = QIcon(os.path.join(os.path.dirname(__file__), 'icon.svg'))
        self.action = QAction(icon, 'ODN Export Information (KMZ / KML)', self.iface.mainWindow())
        self.action.triggered.connect(self.run)
        self.iface.addPluginToMenu('&ODN Export Information', self.action)
        self.iface.addToolBarIcon(self.action)

    def unload(self):
        if self.action:
            self.iface.removePluginMenu('&ODN Export Information', self.action)
            self.iface.removeToolBarIcon(self.action)
            self.action = None

    def run(self):
        try:
            from .dialog import ODNExportDialog
            if self.dialog is None:
                self.dialog = ODNExportDialog(self.iface)
            self.dialog.show()
            self.dialog.raise_()
            self.dialog.activateWindow()
        except Exception as exc:
            QMessageBox.critical(
                self.iface.mainWindow(), 'ODN Export',
                '无法打开插件窗口：\n{}'.format(exc)
            )