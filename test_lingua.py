import ctypes
import os
import re
import sys

# Load libstdc++ from lib folder before importing fasttext
base_dir = os.path.dirname(__file__)
lib_dir = os.path.join(base_dir, "lib")
ctypes.CDLL(os.path.join(lib_dir, "libstdc++.so.6"))

sys.path.insert(0, os.path.join(lib_dir, "fasttext"))
import fasttext

# LOAD MODEL
model = fasttext.load_model(os.path.join(base_dir, "lid.176.ftz"))  # .ftz not .bin

# RAW STRING
text = r"""
1
00:00:00,418 --> 00:00:05,423


2
00:01:33,761 --> 00:01:36,931
車

3
00:01:39,975 --> 00:01:42,186
"""

# CLEAN TEXT
clean_text = re.sub(r"\d+\n\d{2}:\d{2}:\d{2},\d{3} --> .*?\n", "", text)
clean_text = re.sub(r"\{\\.*?\}", "", clean_text)
clean_text = re.sub(r"\s+", " ", clean_text).strip()

# PREDICT
labels, probabilities = model.predict(clean_text, k=3)

for label, prob in zip(labels, probabilities):
    print(label.replace("__label__", ""), prob)