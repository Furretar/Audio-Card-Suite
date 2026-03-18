import os
import re
import sys
import ctypes

base_dir = os.path.dirname(__file__)
lib_dir = os.path.join(base_dir, "lib")
fasttext_lib_dir = os.path.join(lib_dir, "fasttext")

sys.path.insert(0, base_dir)
sys.path.insert(0, fasttext_lib_dir)

ctypes.CDLL(os.path.join(fasttext_lib_dir, "libstdc++.so.6"))

import fasttext

model = fasttext.load_model(os.path.join(fasttext_lib_dir, "lid.176.ftz"))

# RAW STRING
text = r"""
31
00:03:11,358 --> 00:03:15,738
裁判の術式…!!
"""

# CLEAN TEXT
clean_text = re.sub(r"\d+\n\d{2}:\d{2}:\d{2},\d{3} --> .*?\n", "", text)
clean_text = re.sub(r"\{\\.*?\}", "", clean_text)
clean_text = re.sub(r"\s+", " ", clean_text).strip()

print(f"Clean text: '{clean_text}'")

if clean_text:
    labels, probs = model.predict(clean_text, k=5)
    for label, prob in zip(labels, probs):
        print(f"{label.replace('__label__', '')}: {prob:.4f}")
else:
    print("No text to detect")