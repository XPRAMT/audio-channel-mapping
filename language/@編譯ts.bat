@echo off
:: �]�w�ɮ׭p��
set count=0

:: �M����e�ؿ��Ψ�l�ؿ������Ҧ� .ts ���
for /r %%f in (*.ts) do (
    echo �sĶ½Ķ���G%%f
    lrelease %%f
    set /a count+=1
)

:: ��ܧ����T��
echo -----------------------------------
echo �����I�@�sĶ %count% ��½Ķ���C
pause
