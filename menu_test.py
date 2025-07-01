import os
import sys

try:
    from aqt import mw
    from aqt.qt import *
    from aqt.utils import showInfo
    inside_anki = True
except ImportError:
    inside_anki = False
    print("Running outside Anki – using mock `mw`")

    from PyQt6.QtWidgets import (
        QDialog, QVBoxLayout, QGroupBox, QPushButton, QLabel, QLineEdit, QComboBox,
        QSpinBox, QCheckBox, QTabWidget, QWidget, QHBoxLayout, QGridLayout, QSizePolicy, QMessageBox
    )
    from PyQt6.QtCore import Qt
    from PyQt6.QtGui import QIcon

    class MockMW:
        class MockCol:
            class MockModels:
                def by_name(self, name): return True
                def current(self): return {'name': 'Basic'}
            def __init__(self): self.models = self.MockModels()
        def __init__(self): self.col = self.MockCol()
    mw = MockMW()

    def showInfo(msg):
        print("INFO:", msg)

import manage_files

if not inside_anki:
    manage_files.showInfo = showInfo




def detect_format_test():
    sound_line1 = "[sound:Sousou no Frieren - 01`ABCD`00h04m55s719ms-00h04m57s319ms`85-85.mp3]"
    format = manage_files.detect_format(sound_line1)
    # print(f"format: {format}")
    assert format == "backtick"

    sound_line2 = "[sound:Yuru_Camp_S2E07`ABCD`00h07m04s341ms-00h07m07s259ms`1-3`nm.mp3]"
    format2 = manage_files.detect_format(sound_line2)
    # print(f"format2: {format2}")
    assert format2 == "backtick"
detect_format_test()


def extract_sound_line_data_test():
    sound_line1 = "[sound:Yuru_Camp_S2E07`ABCD`00h07m04s341ms-00h07m07s259ms`1-3`nm.mp3]"
    sound_line2 = "[sound:Yuru_Camp_S2E07_00.07.04.341-00.07.07.259.mp3]"

    data = manage_files.extract_sound_line_data(sound_line1)
    data2 = manage_files.extract_sound_line_data(sound_line2)

    timestamp_filename1 = data["timestamp_filename"]
    timestamp_filename2  = data2["timestamp_filename"]

    new_sound_line1 = f'[sound:{timestamp_filename1}]'
    # print(f"{new_sound_line1} == {sound_line1}")
    assert new_sound_line1 == sound_line1

    new_sound_line2 = f'[sound:{timestamp_filename2}]'
    # print(f"{new_sound_line2} == {sound_line2}")
    assert new_sound_line2 == sound_line2
extract_sound_line_data_test()

def get_sound_line_from_block_and_path_test():
    correct_sound_line = "[sound:Sousou no Frieren - 01`ABCD`00h04m55s719ms-00h04m57s319ms`85-85.mp3]"
    sentence_text = "- 因為對國王陛下不敬\n- 我們…我們會再告誡他們的"
    block = [85, "00.04.55.719", "00.04.57.319", sentence_text]
    _, subtitle_path = manage_files.get_subtitle_block_and_subtitle_path_from_sentence_text(sentence_text)
    sound_line = manage_files.get_sound_line_from_subtitle_block_and_path(block, subtitle_path)

    altered_data = manage_files.get_altered_sound_data(sound_line, 0, 0, None)
    # print(altered_data)

    # print(f"{sound_line} == {correct_sound_line}")
    assert sound_line == correct_sound_line

    correct_sound_line2 = "[sound:01 クビキリサイクル 青色サヴァンと戯言遣い`ABCD`10h50m14s026ms-10h50m17s546ms`13498-13498.mp3]"
    sentence_text2 = "服の裏地にスペクトラが縫いこんであるんです。"
    block2 = [13498, "10.50.14.026", "10.50.17.546", sentence_text]
    _, subtitle_path2 = manage_files.get_subtitle_block_and_subtitle_path_from_sentence_text(sentence_text2)
    sound_line2 = manage_files.get_sound_line_from_subtitle_block_and_path(block2, subtitle_path2)
    # print(f"{sound_line2} == {correct_sound_line2}")
    assert sound_line2 == correct_sound_line2
get_sound_line_from_block_and_path_test()

def alter_sound_file_times_test():
    sound_line1 = "[sound:Sousou no Frieren - 01`ABCD`00h04m55s719ms-00h04m57s319ms`85-85.mp3]"
    start_delta = 0
    end_delta = 0
    manage_files.alter_sound_file_times(sound_line1, start_delta, end_delta, None)
    data1 = manage_files.extract_sound_line_data(sound_line1)
    collection_path1 = data1["collection_path"]
    assert True == os.path.exists(collection_path1)

    sound_line2 = "[sound:02_クビシメロマンチスト_人間失格・零崎人識`ABCD`08h44m13s868ms-08h44m16s734ms`10895-10895.mp3]"
    start_delta2 = 0
    end_delta2 = 101
    data2 = manage_files.get_altered_sound_data(sound_line2, start_delta2, end_delta2, 1)
    new_filename = data2["new_filename"],
    print(new_filename)
    # assert True == os.path.exists(collection_path2)
alter_sound_file_times_test()



def add_context_line_test():
    sound_line1 = "[sound:Sousou no Frieren - 01`ABCD`00h04m55s719ms-00h04m57s319ms`85-85.mp3]"
    check_sound_line1 = "[sound:Sousou_no_Frieren_-_01`ABCD`00h04m55s719ms-00h04m58s921ms`85-86.mp3]"
    sentence_text1 = "- 因為對國王陛下不敬\n- 我們…我們會再告誡他們的"
    new_sentence_text_check1 = """- 因為對國王陛下不敬
- 我們…我們會再告誡他們的

- 還差點被處死
- 我來舔您的鞋子吧"""
    relative_index1 = 1
    new_sound_tag1, target_sentence_text1 = menu.get_context_line_data(sound_line1, sentence_text1, relative_index1)
    if relative_index1 == 1:
        new_sentence_text1 = f"{sentence_text1}\n\n{target_sentence_text1}"
    else:
        new_sentence_text1 = f"{target_sentence_text1}\n\n{sentence_text1}"

    print(f"{new_sentence_text_check1}\n==\n{new_sentence_text1}")
    print(f"{new_sound_tag1}\n==\n{check_sound_line1}")
    assert new_sound_tag1 == check_sound_line1
    assert new_sentence_text_check1 == new_sentence_text1

    sound_line2 = "[sound:02_クビシメロマンチスト_人間失格・零崎人識`ABCD`08h44m13s918ms-08h44m16s734ms`10895-10895.mp3]"
    sentence_text2 = "「……別に。見ての通りに人畜無害で極めて大人しい、\n\nただの公明正大な男の子ですから"
    new_sound_line_check2 = "[sound:02_クビシメロマンチスト_人間失格・零崎人識`ABCD`08h44m13s918ms-08h44m20s190ms`10895-10896.mp3]"
    new_sentence_text_check2 = "「……別に。見ての通りに人畜無害で極めて大人しい、\n\nただの公明正大な男の子ですから\n\n「へえ、そうですか」"
    relative_index2 = 1
    new_sound_tag2, target_sentence_text2 = menu.get_context_line_data(sound_line2, sentence_text2, relative_index2)
    if relative_index2 == 1:
        new_sentence_text2 = f"{sentence_text2}\n\n{target_sentence_text2}"
    else:
        new_sentence_text2 = f"{target_sentence_text2}\n\n{sentence_text2}"
    print(f"{new_sentence_text2}\n==\n{new_sentence_text_check2}")
    assert new_sound_tag2 == new_sound_line_check2
    assert new_sentence_text2 == new_sentence_text_check2

    sentence_text3 = "さながら松永弾正のような死に際だっただけに、こうした再会に戸惑いを覚える僕だったが……漫画やなんかではよくある台詞だが、\n\nこれが"
    sound_line3 = ""
    relative_index3 = 1
    new_sound_tag3, new_sentence_text3 = menu.get_context_line_data(sound_line3, sentence_text3, relative_index3)
    print(f"{new_sentence_text3}")
add_context_line_test()

def remove_edge_new_sentence_new_sound_file_test():
    sentence_text1 = "紅茶、\n\nそれもマルコポーロだった"
    sound_line1 = "[sound:02_クビシメロマンチスト_人間失格・零崎人識`ABCD`06h58m17s419ms-06h58m20s989ms`8770-8771.mp3]"
    relative_index1 = 1
    new_sentence_text, new_sound_line = menu.remove_edge_new_sentence_new_sound_file(sound_line1, sentence_text1, relative_index1)
    print(f"{new_sound_line}")
    print(f"{new_sentence_text}\n==\n紅茶、")
    assert new_sentence_text == "紅茶、"


    sentence_text2 = "服装は昨日のサロペット・パンツとは違う。\n\n雪のような真っ白\n\nいベアトップのシャツに、"
    sound_line2 = "[sound:02_クビシメロマンチスト_人間失格・零崎人識`ABCD`08h14m03s990ms-08h14m09s786ms`10287-10288.mp3]"
    relative_index2 = -1
    new_sentence_text2, new_sound_line2 = menu.remove_edge_new_sentence_new_sound_file(sound_line2, sentence_text2, relative_index2)
    assert new_sentence_text2 == "雪のような真っ白\n\nいベアトップのシャツに、"
    
    sentence_text3 = "省線の吊皮には疥癬の虫がうようよ、\n\nまたは、\n\nおさしみ、"
    sentence_text_check3 = "省線の吊皮には疥癬の虫がうようよ、\n\nまたは、"
    sound_line_check3 = "[sound:太宰治_-_西村俊彦`ABCD`03h30m30s004ms-03h30m32s820ms`3804-3804.mp3]"
    sound_line3 = "[sound:太宰治 - 西村俊彦`ABCD`03h30m30s004ms-03h30m37s408ms`3804-3805.mp3]"
    relative_index3 = 1
    new_sentence_text3, new_sound_line3 = menu.remove_edge_new_sentence_new_sound_file(sound_line3, sentence_text3, relative_index3)
    
    print(f"{new_sentence_text3}\n==\n{sentence_text_check3}")
    assert new_sentence_text3 == sentence_text_check3
    print(f"{new_sound_line3}\n==\n{sound_line_check3}")
    assert new_sound_line3 == sound_line_check3

remove_edge_new_sentence_new_sound_file_test()

def get_valid_backtick_sound_line_test():
    sound_line1 = "[sound:Sousou no Frieren - 01`ABCD`00h04m55s719ms-00h04m57s319ms`85-85.mp3]"
    sentence_text1 = "- 因為對國王陛下不敬\n- 我們…我們會再告誡他們的"
    sound_line, block = manage_files.get_valid_backtick_sound_line_and_block(sound_line1, sentence_text1)
    new_sound_line = manage_files.alter_sound_file_times(sound_line, 0, 0, None)
    # print(f"new_sound_line: {new_sound_line}")
    
    
    sound_line2 = "[sound:55_00.13.41.872-00.13.47.418.mp3]"
    sound_line_check2 = "[sound:55`ABCD`00h13m42s215ms-00h13m44s759ms`208-208.mp3]"
    sentence_text2 = "找到一息尚存的團長的時候 我本來想給他一個痛快"
    new_sound_line2, block2 = manage_files.get_valid_backtick_sound_line_and_block(sound_line2, sentence_text2)
    print(f"new_sound_line2: {new_sound_line2}")
    assert sound_line_check2 == new_sound_line2
    
    sound_line3 = "[sound:Sousou_no_Frieren_-_01`ABCD`00h04m55s719ms-00h04m58s921ms`85-86.mp3]"
    sentence_text3 = "- 因為對國王陛下不敬"
    block, subtitle_path = manage_files.get_block_and_subtitle_file_from_sentence_text(sentence_text3)
    print(f"block: {block}, subtitle_path: {subtitle_path}")
    new_sound_line3, block3 = manage_files.get_valid_backtick_sound_line_and_block(sound_line3, sentence_text3)
    print(f"new_sound_line3: {new_sound_line3}")
    print(f"block3: {block3}")
get_valid_backtick_sound_line_test()


def generate_fields_test():
    sound_line1 = ""
    sentence_text1 = """- 因為對國王陛下不敬 - 我們…我們會再告誡他們的"""
    menu.generate_fields_sound_sentence_image_translation(sound_line1, 2, sentence_text1, 0, "", 3)
generate_fields_test()

# "[sound:Sousou_no_Frieren_-_01_00.04.55.719-00.04.58.921.mp3]"