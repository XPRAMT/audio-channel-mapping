@echo off
:: 設定檔案計數
set count=0

:: 遍歷當前目錄及其子目錄中的所有 .ts 文件
for /r %%f in (*.ts) do (
    echo 編譯翻譯文件：%%f
    lrelease %%f
    set /a count+=1
)

:: 顯示完成訊息
echo -----------------------------------
echo 完成！共編譯 %count% 個翻譯文件。
pause
