Extracting initramfs.tar.gz from the XDJ-RX3 Source Archive

The source package is distributed as two ZIP files:

A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
57CB205B-D45A-4143-BC09-22D8400074C2.zip

Each ZIP contains one part of a split tar.bz2 archive.

The goal is to reconstruct the archive, extract it, run make_rootfs, and obtain:

initramfs.tar.gz

1. Install 7-Zip

On macOS:

brew install sevenzip

2. Extract both ZIP files

Create a working directory:

mkdir rx3-source
cd rx3-source

Extract both archives:

7zz x ../A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
7zz x ../57CB205B-D45A-4143-BC09-22D8400074C2.zip

You should now have:

pioneerdj_xdj_rx3.tar.bz2.00
pioneerdj_xdj_rx3.tar.bz2.01

3. Reassemble the split archive

Concatenate both parts in order:

cat \
  pioneerdj_xdj_rx3.tar.bz2.00 \
  pioneerdj_xdj_rx3.tar.bz2.01 \
  > pioneerdj_xdj_rx3.tar.bz2

Optionally verify the reconstructed archive:

bzip2 -tv pioneerdj_xdj_rx3.tar.bz2

Expected result:

pioneerdj_xdj_rx3.tar.bz2: ok

4. Extract the reconstructed archive

mkdir source
tar -xjf pioneerdj_xdj_rx3.tar.bz2 -C source
cd source

5. Locate make_rootfs

Search for the script:

find . -name make_rootfs

Move to the directory containing it.

For example:

cd path/to/directory

Make it executable if necessary:

chmod +x make_rootfs

6. Run make_rootfs

Run:

./make_rootfs

The script calls LTIB internally:

./ltib --deploy

This step should be performed in a Linux environment compatible with the LTIB build system used by the source package.

Running this part directly on macOS is not expected to work reliably.

7. Locate the generated initramfs

Once make_rootfs has completed successfully:

find . -name initramfs.tar.gz

The resulting file:

initramfs.tar.gz

is the generated initramfs.

Process overview

A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
57CB205B-D45A-4143-BC09-22D8400074C2.zip
        |
        v
      7-Zip
        |
        v
pioneerdj_xdj_rx3.tar.bz2.00
pioneerdj_xdj_rx3.tar.bz2.01
        |
        v
       cat
        |
        v
pioneerdj_xdj_rx3.tar.bz2
        |
        v
    tar -xjf
        |
        v
   source tree
        |
        v
   make_rootfs
        |
        v
initramfs.tar.gz