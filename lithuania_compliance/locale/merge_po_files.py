#!/usr/bin/env python3
"""
Merge multiple .po files into a single consolidated .po file since Frappe disregards meta data in .po files, and uses filename to identify language files.
"""

import os
import re
import sys
from collections import OrderedDict
from pathlib import Path


def parse_po_file(filepath):
	"""
	Parse a .po file and return a dictionary of translations.
	Returns: (header, translations_dict)
	"""
	translations = OrderedDict()
	header = ""
	current_msgid = None
	current_msgstr = None
	in_header = True

	with open(filepath) as f:
		lines = f.readlines()

	i = 0
	while i < len(lines):
		line = lines[i]

		# Capture header
		if in_header and line.startswith('msgstr ""'):
			# Read header content
			i += 1
			while i < len(lines) and (lines[i].startswith('"') or lines[i].strip() == ""):
				if lines[i].startswith('"'):
					header += lines[i]
				i += 1
			in_header = False
			continue

		# Parse msgid
		if line.startswith("msgid "):
			if current_msgid is not None and current_msgstr is not None:
				# Store previous translation only if msgstr is not empty
				if current_msgid and current_msgstr != '""':
					translations[current_msgid] = current_msgstr

			# Extract msgid value
			current_msgid = line[6:].strip()
			current_msgstr = None

			# Handle multi-line msgid
			i += 1
			while i < len(lines) and lines[i].startswith('"'):
				current_msgid += lines[i].rstrip()
				i += 1
			continue

		# Parse msgstr
		elif line.startswith("msgstr "):
			current_msgstr = line[7:].strip()

			# Handle multi-line msgstr
			i += 1
			while i < len(lines) and lines[i].startswith('"'):
				current_msgstr += lines[i].rstrip()
				i += 1
			continue

		i += 1

	if current_msgid is not None and current_msgstr is not None and current_msgid and current_msgstr != '""':
		translations[current_msgid] = current_msgstr

	return header, translations


def merge_po_files(input_files, output_file):
	"""
	Merge multiple .po files into a single file.

	Args:
	    input_files: List of input .po file paths
	    output_file: Path to output .po file
	"""
	merged_translations = OrderedDict()
	header = None

	# Parse all input files
	for input_file in input_files:
		if not os.path.exists(input_file):
			print(f"Warning: File not found: {input_file}")
			continue

		print(f"Processing: {input_file}")
		file_header, translations = parse_po_file(input_file)

		if header is None and file_header:
			header = file_header

		#! Merge translations (later files override earlier ones)
		merged_translations.update(translations)

	with open(output_file, "w", encoding="utf-8") as f:
		# File header
		f.write('msgid ""\n')
		f.write('msgstr ""\n')
		if header:
			f.write(header)
		else:
			f.write('"Content-Type: text/plain; charset=UTF-8\\n"\n')
			f.write('"Language: lt\\n"\n')
		f.write("\n")

		for msgid, msgstr in merged_translations.items():
			msgid_parts = re.findall(r'"(?:[^"\\]|\\.)*"', msgid)
			f.write(f"msgid {msgid_parts[0]}\n")
			for part in msgid_parts[1:]:
				f.write(f"{part}\n")

			msgstr_parts = re.findall(r'"(?:[^"\\]|\\.)*"', msgstr)
			f.write(f"msgstr {msgstr_parts[0]}\n")
			for part in msgstr_parts[1:]:
				f.write(f"{part}\n")

			f.write("\n")

	print(f"✓ Merged {len(input_files)} files with {len(merged_translations)} translations")


def main():
	files_dir = Path(__file__).parent / "files"
	po_files = sorted([str(f) for f in files_dir.glob("*.po") if f.is_file()])

	if not po_files:
		print("Error: No .po files found in the files directory")
		sys.exit(1)

	output_file = str(Path(__file__).parent / "lt.po")

	print(f"Found {len(po_files)} .po files:")
	for f in po_files:
		print(f" - {f}")

	merge_po_files(po_files, output_file)
	print(f"Success! Merged file: {output_file}")


if __name__ == "__main__":
	main()
