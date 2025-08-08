from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from io import BytesIO
from struct import pack, unpack
from typing import Any, BinaryIO, Self, Optional
import posixpath as path
import os
import zlib

__all__: list[str] = [
	'VFS',
	'VFile',
	'VDirectory',
	'VEntry'
]


def hash_name(string: str, do_preceding_path_check: bool = True) -> int:
	if not string.startswith('/') and do_preceding_path_check:
		string = '/' + string

	hashed: int = 5381
	for char in string.lower():
		hashed = ((hashed << 5) + hashed) + ord(char)

	return hashed & 0x3FFFFFFF | 0x40000000


def read_int(fp: BinaryIO) -> int:
	return unpack('<i', fp.read(4))[0]


def read_string(fp: BinaryIO) -> str:
	str_len: int = read_int(fp)
	return fp.read(str_len).decode()


def write_int(fp: BinaryIO, val: int) -> None:
	fp.write(pack('<i', val))


def write_string(fp: BinaryIO, string: str) -> None:
	write_int(fp, len(string))
	fp.write(string.encode())


@dataclass(kw_only=True)
class VEntry(ABC):
	name_hash: int
	id: int
	parent_id: int
	name: str | None
	parent: Optional['VDirectory'] = field(repr=False) # ugly old skool typing

	@classmethod
	@abstractmethod
	def read(cls, fp: BinaryIO) -> Self:
		pass

	@property
	def path(self) -> str:
		return path.join(
			self.parent.path if self.parent is not None else '',
			self.name
		)

	@abstractmethod
	def write(self, fp: BinaryIO) -> None:
		pass


@dataclass(kw_only=True)
class VFile(VEntry):
	compress_type: int
	offset: int
	size: int

	@classmethod
	def read(cls, fp: BinaryIO) -> Self:
		return cls(
			name_hash=read_int(fp),
			id=read_int(fp),
			compress_type=read_int(fp),
			parent_id=read_int(fp),
			offset=read_int(fp),
			size=read_int(fp),
			name=None,
			parent=None
		)

	def write(self, fp: BinaryIO) -> None:
		write_int(fp, self.name_hash)
		write_int(fp, self.id)
		write_int(fp, self.compress_type)
		write_int(fp, self.parent_id)
		write_int(fp, self.offset)
		write_int(fp, self.size)


@dataclass(kw_only=True)
class VDirectory(VEntry):
	unk1: int
	file_id_start: int
	entries: list[VEntry] = field(repr=False)

	@classmethod
	def read(cls, fp: BinaryIO) -> Self:
		return cls(
			name_hash=read_int(fp),
			id=read_int(fp),
			parent_id=read_int(fp),
			unk1=read_int(fp),
			file_id_start=read_int(fp),
			entries=[],
			name=None,
			parent=None
		)

	@property
	def folders(self) -> list[Self]:
		return [entry for entry in self.entries if isinstance(entry, VDirectory)]

	@property
	def files(self) -> list[VFile]:
		return [entry for entry in self.entries if isinstance(entry, VFile)]

	def write(self, fp: BinaryIO) -> None:
		write_int(fp, self.name_hash)
		write_int(fp, self.id)
		write_int(fp, self.parent_id)
		write_int(fp, self.unk1)
		write_int(fp, self.file_id_start)


class VFS:
	def __init__(self, file_name: str, root_folder: str) -> None:
		self.file_name: str = file_name
		self.root_folder: str = root_folder
		self.folders: list[VDirectory] = []
		self.files: list[VFile] = []
		self.fp: BinaryIO | None = None
		self.name_table_offset: int | None = None
		self.data_offset: int | None = None
		self.root_id: int | None = None

	def __enter__(self) -> Self:
		if self.fp is not None and self.fp.closed:
			raise Exception('file is closed')
		return self

	def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
		self.close()

	def close(self) -> None:
		if self.fp is not None:
			self.fp.close()

	def load_file(self) -> None:
		self.fp = open(self.file_name, 'rb')

		# header check
		if self.fp.read(4) != b'VFS2':
			raise Exception('input is not a VFS2 archive')

		# parse folders
		num_folders: int = read_int(self.fp)
		for _ in range(num_folders):
			self.folders.append(VDirectory.read(self.fp))
		self.folders.sort(key=lambda f: f.id)

		# parse files
		num_files: int = read_int(self.fp)
		for _ in range(num_files):
			self.files.append(VFile.read(self.fp))
		self.files.sort(key=lambda f: f.id)

		# get offsets
		self.name_table_offset = read_int(self.fp)
		self.data_offset = self.fp.tell()

		# parse names
		self.fp.seek(self.name_table_offset, 0)

		# parse file and folder names
		num_file_names: int = read_int(self.fp)
		if num_file_names != num_files:
			raise Exception('number of file and file names do not match')

		for file in self.files:
			file.name = read_string(self.fp)

		num_folder_names: int = read_int(self.fp)
		if num_folder_names != num_folders:
			raise Exception('number of folder and folder names do not match')

		for folder in self.folders:
			folder.name = read_string(self.fp)

		self.set_relations()

	def load_folder(self) -> None:
		self.root_id = self.add_folder('', -1, 0)

		paths = []
		for root, dirs, files in os.walk(self.root_folder, topdown=True):
			paths.append((root, dirs, files))

		paths.sort(key=lambda t: t[0].count('/'))

		folder_map: dict[str, int] = {'': self.root_id}
		for root, folders, files in paths:
			folders.sort(); files.sort()
			name: str = root.lstrip(self.root_folder).lstrip('/')

			folder_id: int = folder_map.get(name)
			for subfolder in folders:
				subfolder_name: str = path.join(name, subfolder)
				subfolder_id: int = self.add_folder(subfolder, folder_id, hash_name(subfolder_name))
				folder_map[subfolder_name] = subfolder_id

			for file in files:
				if file == '.DS_Store': continue
				file_name: str = path.join(name, file)
				self.add_file(file, folder_id, hash_name(file_name))

		self.set_relations()

	def add_folder(self, name: str, parent_id: int, name_hash: int) -> int:
		folder_id: int = len(self.folders)

		unk1: int
		match name:
			case '':
				unk1 = 1
			case 'ui':
				unk1 = 9
			case _:
				unk1 = -1

		self.folders.append(VDirectory(
			name_hash=name_hash,
			id=folder_id,
			parent_id=parent_id,
			unk1=unk1,
			file_id_start=-1,
			entries=[],
			name=name,
			parent=None
		))

		return folder_id

	def add_file(self, name: str, parent_id: int, name_hash: int) -> int:
		file_id: int = len(self.files)
		compress_type: int = 0 if name.endswith('.at9') else 2

		self.files.append(VFile(
			name_hash=name_hash,
			id=file_id,
			compress_type=compress_type,
			parent_id=parent_id,
			offset=-1,
			size=-1,
			name=name,
			parent=None
		))

		return file_id

	def set_relations(self) -> None:
		# set folder parents and entries
		for folder in self.folders:
			if folder.parent_id >= 0:
				parent: VDirectory = self.folders[folder.parent_id]
				folder.parent = parent
				parent.entries.append(folder)
			else:
				self.root_id = folder.id

		# set file parents
		for file in self.files:
			if file.parent_id >= 0:
				parent: VDirectory = self.folders[file.parent_id]
				if parent.id != file.parent_id:
					raise Exception(
						f'"{file.name}" has mismatched parent id: '
						f'expected {file.parent_id}, but got {parent.id}'
					)
				file.parent = parent
				parent.entries.append(file)
			else:
				raise Exception(f'"{file.name}" does not have parent folder')

	def extract(self) -> None:
		os.makedirs(self.root_folder, exist_ok=True)

		if self.root_id is None:
			raise Exception('no root folder initialised')

		root: VDirectory = self.folders[self.root_id]
		old_root_name: str | None = root.name
		root.name = path.join(self.root_folder, root.name)

		try:
			self.extract_folder(root)
		finally:
			root.name = old_root_name

	def extract_folder(self, folder: VDirectory) -> None:
		os.makedirs(folder.path, exist_ok=True)

		for file in folder.files:
			self.fp.seek(self.data_offset + file.offset, 0)
			decompressed_size: int | None = None

			if file.compress_type > 0:
				decompressed_size = read_int(self.fp)

			data: bytes = self.fp.read(file.size)

			match file.compress_type:
				case 0: pass
				case 2:
					data = zlib.decompress(data)
					if len(data) != decompressed_size:
						raise Exception('decompressed size does not match')
				case _:
					raise Exception(f'unknown compression type {file.compress_type}')

			with open(file.path, 'wb') as fp:
				fp.write(data)

		for subfolder in folder.folders:
			self.extract_folder(subfolder)

	def compress(self) -> None:
		self.fp = open(self.file_name, 'wb')

		if self.root_id is None:
			raise Exception('no root folder initialised')

		root: VDirectory = self.folders[self.root_id]
		old_root_name: str | None = root.name
		root.name = path.join(self.root_folder, root.name)

		try:
			buf: BytesIO = BytesIO()
			self.compress_folder(buf, root)

			# write header
			self.fp.write(b'VFS2')

			# write folder data
			write_int(self.fp, len(self.folders))
			for folder in self.folders:
				folder.write(self.fp)

			# write file data
			write_int(self.fp, len(self.files))
			for file in self.files:
				file.write(self.fp)

			# write and set offsets
			self.name_table_offset = self.fp.tell() + 4 + buf.getbuffer().nbytes
			write_int(self.fp, self.name_table_offset)
			self.data_offset = self.fp.tell()

			# write data
			buf.seek(0)
			self.fp.write(buf.read())

			# write file and folder names
			write_int(self.fp, len(self.files))
			for file in self.files:
				write_string(self.fp, file.name)

			write_int(self.fp, len(self.folders))
			for folder in self.folders:
				write_string(self.fp, folder.name)

		finally:
			root.name = old_root_name

	def compress_folder(self, buf: BinaryIO, folder: VDirectory) -> None:
		for file in folder.files:
			if folder.file_id_start < 0:
				folder.file_id_start = file.id

			offset: int = buf.tell()

			with open(file.path, 'rb') as fp:
				data: bytes = fp.read()

			match file.compress_type:
				case 0:
					data = data  # pycharm gives me a stern warning without this
				case 2:
					write_int(buf, len(data))
					data = zlib.compress(data, level=1)
				case _:
					raise Exception(f'unknown compression type {file.compress_type}')

			buf.write(data)
			file.offset = offset
			file.size = len(data)

		for subfolder in folder.folders:
			self.compress_folder(buf, subfolder)
