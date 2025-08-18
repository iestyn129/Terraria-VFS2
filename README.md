# Terraria VFS2
A quick and dirty tool for extracting and compressing VFS2 archives used by numerous old-gen console versions of Terraria.

Older versions of Terraria use an older version of VFS2, this tool is only intended for PS Vita 1.11.

## Usage
For extracting run:
```shell
python main.py extract input.vfs output_folder
```
`extract` and be shortened to `e`.

For compressing run:
```shell
python main.py compress output.vfs input_folder
```
`compress` and be shortened to `c`.

## Known Issues
Setting the unknown flag of folders is still hardcoded as it is unknown what they do or how to choose which ones.

## Thanks
Huge thanks to [LITTOMA](https://github.com/LITTOMA) and their [vfs2](https://github.com/LITTOMA/vfs2) tool for doing the initial research on VFS2 archives.

## Disclaimer
>This project is an unofficial program designed for use with Terraria files.
>All trademarks, logos, and copyrighted materials are the property of their respective owners.
>This tool is not affiliated with, endorsed by, or sponsored by Re-Logic.
>Use of this tool is at your own risk. Please respect the terms of service and other agreements of the original game.
