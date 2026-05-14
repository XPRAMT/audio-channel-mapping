call ../.venv/Scripts/activate
echo 啟動虛擬環境
pip list
nuitka GUI.pyw --standalone ^
--windows-console-mode=disable ^
--include-data-dir=..\.venv\Lib\site-packages\zeroconf=zeroconf ^
--windows-icon-from-ico=icon/icon.ico ^
--output-filename=GUI ^
--enable-plugin=pyqt6 ^
--remove-output ^
--follow-imports
pause