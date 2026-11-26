"""Интерфейсный тест для запущенного сервиса. Требует Playwright и Chrome."""
import csv

import tempfile
from pathlib import Path

from playwright.sync_api import sync_playwright, expect
from journal import load_workbook


def run():
    with sync_playwright() as pw, tempfile.TemporaryDirectory() as tmp:
        browser = pw.chromium.launch(channel="chrome",headless=True)
        page = browser.new_page(accept_downloads=True)
        page.set_default_timeout(6000)
        errors = []
        page.on("pageerror",lambda e: errors.append(str(e)))
        page.goto("http://127.0.0.1:8765")
        rows = page.locator("#report tr[data-index]")
        def verify(expected):
            expect(rows).to_have_count(len(expected))
            for row,(residual,status) in zip(rows.all(),expected):
                expect(row.locator("td").nth(3)).to_have_text(residual)
                expect(row.locator("td").last).to_have_text(status)
        def check():
            page.locator("#check").click()
            expect(page.locator("#journalResult")).to_be_visible()
        def upload_file(path):
            with page.expect_response("**/api/journal-load") as response:
                page.locator("#journalFile").set_input_files(path)
            assert response.value.ok
            expect(page.locator("#importPanel")).to_be_visible()
        def csv_file(text):
            path = Path(tmp)/"shift.csv"
            path.write_text(text,encoding="utf-8-sig")
            upload_file(path)
        high,ok,missing,unknown="Превышен допуск","В пределах допуска","Уточнить данные","Допуск не указан"
        expect(page.locator("#journal")).to_be_visible()
        expect(page.locator("#selector")).to_be_hidden()
        page.locator("#demo").click()
        verify([("+10",high),("+1",ok)])
        rows.first.click()
        expect(page.locator(".trace")).to_contain_text("100 − 70 − 20 = 10 м³")
        expect(page.locator("#resultSource")).to_contain_text("Учебные данные")
        with page.expect_download() as event:
            page.locator("#export").click()
        with open(event.value.path(),encoding="utf-8-sig") as f:
            exported=list(csv.reader(f,delimiter=";"))
        assert len(exported)==3 and exported[1][4]=="10" and exported[2][4]=="1"
        with page.expect_download() as event:
            page.locator('a[download="journal.xlsx"]').click()
        path=Path(tmp)/"исправленный.xlsx"
        event.value.save_as(path)
        book=load_workbook(path)
        book.active["E2"]=30
        extra=book.create_sheet("Весь канал")
        extra.append(["Период","Вход","Выход","Отбор","Допуск канала"])
        extra.append(["Смена 1",100,69,30,2])
        book.save(path)
        upload_file(path)
        check()
        verify([("0",ok),("+1",ok)])
        expect(page.locator("#resultSource")).to_contain_text("Загруженные данные")
        page.locator("#worksheet").select_option("Весь канал")
        expect(page.locator("#sourceFile")).to_contain_text("Весь канал")
        check()
        verify([("+1",ok)])
        expect(rows.first).to_contain_text("A–C")
        headers="Период;Вход;Выход;Отбор;Допуск канала\n"
        csv_file(headers+"С1;100;69;;2\nС2;100;69;0;2\nС3;100;100,5;0;\n")
        check()
        verify([("—",missing),("+31",high),("-0,5",unknown)])
        rows.first.click()
        expect(page.locator(".trace")).to_contain_text("пустая ячейка")
        expect(page.locator("#indicators b")).to_have_text(["3","1","2"])
        csv_file("Дата;Подача, л;Выход, л\nС1;3000;3500\n")
        page.locator("#journalUnit").select_option("l")
        page.locator("#none_ac").check()
        page.locator("#fixed_ac").fill("200")
        check()
        verify([("-0,5",high)])
        page.locator("#journalUnit").select_option("m3")
        check()
        verify([("—",missing)])
        rows.first.click()
        expect(page.locator(".trace")).to_contain_text("единицы несовместимы")
        csv_file("Дата;Подача;Выход;Ед. изм.\nС1;20;19;м³\nС2;20;19;л\n")
        page.locator("#none_ac").check()
        check()
        verify([("+1",unknown),("—",missing)])
        for kind in ("counter","rate"):
            page.locator("#journalKind").select_option(kind)
            expect(page.locator("#check")).to_be_disabled()
            expect(page.locator("#typeHint")).to_be_visible()
        csv_file("Дата;Вход, м³/с;Выход\nС1;20;19\n")
        page.locator("#none_ac").check()
        check()
        verify([("—",missing)])
        rows.first.click()
        expect(page.locator(".trace")).to_contain_text("Интегрируйте расход")
        csv_file("Код;Голова;Хвост;Насос 1;Насос 2\nНочь;60;52;2;3\n")
        for k,i in zip(["period","a","c"],["0","1","2"]):
            page.locator("#point_"+k).select_option(i)
        for i in ["3","4"]:
            page.locator("#add_ac").click()
            page.locator("#takes_ac select").last.select_option(i)
        check()
        verify([("+3",unknown)])
        csv_file(headers+"С1;100;69;20;2\nС1;200;100;30;2\n")
        check()
        verify([("—",missing),("—",missing)])
        rows.first.click()
        expect(page.locator(".trace")).to_contain_text("Дубликат смены в строках 2, 3")
        page.get_by_role("button",name="Проверка метода",exact=True).click()
        expect(page.locator("#experiment")).to_be_visible()
        page.get_by_role("button",name="Эффект ремонта",exact=True).click()
        expect(page.locator("#benefit")).to_be_visible()
        assert not errors,errors
        browser.close()
        print("OK: пример, объяснение, экспорт, правка Excel, лист без B, CSV, единицы, пропуски, дубли, режимы, произвольные заголовки и два отбора.")


if __name__=="__main__":
    run()


