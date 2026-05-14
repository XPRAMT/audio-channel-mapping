@echo off
:: 將 GUI.pyw 重命名為 GUI.py
rename GUI.pyw GUI.py
:: 執行 pylupdate6 命令，更新翻譯文件
pylupdate6 GUI.py -ts translations.ts
:: 將 GUI.py 再次重命名回 GUI.pyw
rename GUI.py GUI.pyw
:: 提示完成
echo Translation update complete!
pause
