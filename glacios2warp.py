#!/usr/bin/env python3

from pathlib import Path
import re

import numpy as np
import mrcfile
import click
import mdocspoofer


def scrape_dir(path, basename=None):
    dir_path = Path(path)
    if basename is None:
        basename = dir_path.name

    basename_n = rf'{basename}(?:_\d)?'

    mrc_re = re.compile(f'{basename_n}.mrc')
    rawtlt_re = re.compile(f'{basename_n}.rawtlt')
    txt_re = re.compile(f'{basename_n}.txt')

    mrc_files = []
    meta_files = []
    tilt_files = []

    for f in dir_path.iterdir():
        if match := mrc_re.search(str(f)):
            mrc_files.append(f)
        elif match := txt_re.search(str(f)):
            meta_files.append(f)
        elif match := rawtlt_re.search(str(f)):
            tilt_files.append(f)

    mrc_files.sort()
    meta_files.sort()
    tilt_files.sort()

    return zip(mrc_files, meta_files, tilt_files)


def split_mrc(mrc_file, meta_file, tilt_file, tilt_series_basename, target_dir):
    start_angle_re = re.compile('Start tilt angle.*?([+-]?\d+\.\d+)')
    min_angle_re = re.compile('Max negative tilt.*?([+-]?\d+\.\d+)')
    max_angle_re = re.compile('Max positive tilt.*?([+-]?\d+\.\d+)')
    step_re = re.compile('Low tilt step.*?([+-]?\d+\.\d+)')
    step_high_re = re.compile('High tilt step.*?([+-]?\d+\.\d+)')

    meta = {}
    with open(meta_file, 'r', encoding='utf-8', errors='ignore') as f:
        for line in f.readlines():
            if match := start_angle_re.search(line):
                start_angle = float(match.group(1))
            elif match := step_re.search(line):
                step = float(match.group(1))
            elif match := step_high_re.search(line):
                step_high = float(match.group(1))
            elif match := min_angle_re.search(line):
                min_angle = float(match.group(1))
            elif match := max_angle_re.search(line):
                max_angle = float(match.group(1))

    with open(tilt_file, 'r', encoding='utf-8', errors='ignore') as f:
        angles = [round(float(x.strip()), 1) for x in f.readlines()]
        start_idx = angles.index(start_angle) + 1
        order = [i for i in range(start_idx, len(angles))] + [i for i in range(0, start_idx)]

    with mrcfile.mmap(mrc_file) as mrc:
        n_slices = mrc.data.shape[0]
        slices = np.vsplit(mrc.data, n_slices)
        for order_idx, image, angle in zip(order, slices, angles):
            filepath = target_dir / f'{tilt_series_basename}_{order_idx:03}[{angle}]_fractions.mrc'
            tilt_image = mrcfile.new(filepath, image)
            tilt_image.close()
            click.echo(f'Writing out {filepath.absolute()}...')


@click.command()
@click.option('--input-dir', '-i', 'dir_path',
              type=click.Path(),
              default='.',
              help='Directory containing glacios data. If empty, default is this directory.',
              )
@click.option('--basename', '-b', 'basename',
              type=str,
              help='Base name of the input files, used to collect the right files. If empty, default is dirname.',
              )
@click.option('--output-dir', '-o', 'target_dir',
              type=click.Path(),
              help='Output directory. If empty, a subdir called "glacios2warp" is made in the input dir.',
              )
@click.option('--dose-per-image', '-d', 'dose_per_image',
              type=float,
              help='Dose per image (electrons per square angstrom)',
              )
@click.option('--target-basename', '-tb', 'target_basename',
              type=str,
              help='Base name of the output files. If empty, default is basename.',
              )
def main(dir_path, basename=None, target_dir=None, dose_per_image=None, target_basename=None):
    # sanity checks
    dir_path = Path(dir_path)
    if not dir_path.is_dir():
        raise ValueError(f'path is not a directory')
    if target_dir is None:
        target_dir = dir_path / 'glacios2warp'
    else:
        target_dir = Path(target_dir)
    target_dir.mkdir(parents=True, exist_ok=True)
    if dose_per_image is None:
        raise ValueError('You must give a dose per image')
    if target_basename is None:
        target_basename = basename

    # split the data
    for idx, (image, data, tilt) in enumerate(scrape_dir(dir_path, basename)):
        tit_series_basename = f'{basename}_TS_{idx:03}'
        split_mrc(image, data, tilt, tit_series_basename, target_dir)

    # spoof the mdocs
    click.echo(f'Spoofing...')
    mdocspoofer.mdoc.FramesDir(target_dir, dose_per_image)
    click.echo(f"Done! You'll find everything in {target_dir.absolute()}")

if __name__ == '__main__':
    main()
