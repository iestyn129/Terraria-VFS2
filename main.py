from sys import argv
from vfs import VFS, hash_name
import posixpath as path


def main() -> None:
	if len(argv) < 4:
		print(f'usage: python {argv[0]} <e[xtract]|c[ompress]> <data.vfs> <vfs_folder>')
		return

	mode: str = argv[1]
	input_vfs: str = argv[2]
	vfs_folder: str = argv[3]

	with VFS(input_vfs, vfs_folder) as vfs:
		match mode[0].lower():
			case 'e':
				vfs.load_file()
				vfs.extract()
				print(f'successfully extracted to {vfs_folder}')
			case 'c':
				vfs.load_folder()
				vfs.compress()
				print(f'successfully compressed to {input_vfs}')
			case _:
				print(f'unsupported mode: {mode}')


if __name__ == '__main__':
	main()
