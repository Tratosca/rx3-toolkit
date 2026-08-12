# Extracting `initramfs.tar.gz` from the XDJ-RX3 Source Package

The XDJ-RX3 source package is distributed as two ZIP files:

```text
A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
57CB205B-D45A-4143-BC09-22D8400074C2.zip
```

Each ZIP contains one part of a split `tar.bz2` archive.

The extraction process is:

```text
ZIP files
   ↓
split .tar.bz2 parts
   ↓
reassembled .tar.bz2
   ↓
source tree
   ↓
make_rootfs
   ↓
initramfs.tar.gz
```

The archive extraction and `make_rootfs` steps can be performed on **macOS or Linux**.

On Windows, the archive can be extracted natively, while the `make_rootfs` step is best performed through **WSL2**.

---

## 1. Extract the two ZIP files

The ZIP files use **Deflate64**, so 7-Zip is recommended.

### macOS

Install 7-Zip:

```bash
brew install sevenzip
```

Create a working directory and extract both files:

```bash
mkdir rx3-source
cd rx3-source

7zz x ../A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
7zz x ../57CB205B-D45A-4143-BC09-22D8400074C2.zip
```

### Linux

Install 7-Zip.

Debian / Ubuntu:

```bash
sudo apt update
sudo apt install 7zip
```

Fedora:

```bash
sudo dnf install 7zip
```

Then extract both files:

```bash
mkdir rx3-source
cd rx3-source

7zz x ../A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
7zz x ../57CB205B-D45A-4143-BC09-22D8400074C2.zip
```

On some distributions, the executable may be named `7z` instead of `7zz`.

### Windows

Install 7-Zip, then open PowerShell in the directory containing the ZIP files.

```powershell
mkdir rx3-source
cd rx3-source

& "C:\Program Files\7-Zip\7z.exe" x ..\A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
& "C:\Program Files\7-Zip\7z.exe" x ..\57CB205B-D45A-4143-BC09-22D8400074C2.zip
```

After extraction, you should have:

```text
pioneerdj_xdj_rx3.tar.bz2.00
pioneerdj_xdj_rx3.tar.bz2.01
```

---

## 2. Reassemble the split archive

The two files are consecutive parts of the same `tar.bz2` archive.

### macOS / Linux

```bash
cat \
  pioneerdj_xdj_rx3.tar.bz2.00 \
  pioneerdj_xdj_rx3.tar.bz2.01 \
  > pioneerdj_xdj_rx3.tar.bz2
```

### Windows

Using `cmd.exe`:

```cmd
copy /b pioneerdj_xdj_rx3.tar.bz2.00+pioneerdj_xdj_rx3.tar.bz2.01 pioneerdj_xdj_rx3.tar.bz2
```

---

## 3. Verify the reconstructed archive

This step is optional but recommended.

### macOS / Linux

```bash
bzip2 -tv pioneerdj_xdj_rx3.tar.bz2
```

Expected output:

```text
pioneerdj_xdj_rx3.tar.bz2: ok
```

### Windows

Using 7-Zip:

```powershell
& "C:\Program Files\7-Zip\7z.exe" t pioneerdj_xdj_rx3.tar.bz2
```

Expected output:

```text
Everything is Ok
```

---

## 4. Extract the reconstructed archive

### macOS / Linux

```bash
mkdir source
tar -xjf pioneerdj_xdj_rx3.tar.bz2 -C source
cd source
```

### Windows

Recent Windows versions include `tar`:

```powershell
mkdir source
tar -xjf pioneerdj_xdj_rx3.tar.bz2 -C source
cd source
```

Alternatively, use 7-Zip:

```powershell
& "C:\Program Files\7-Zip\7z.exe" x pioneerdj_xdj_rx3.tar.bz2
& "C:\Program Files\7-Zip\7z.exe" x pioneerdj_xdj_rx3.tar
```

At this point, the XDJ-RX3 source tree has been extracted.


---

## 5. Run `make_rootfs`

### macOS / Linux

Change to the extracted directory, containing `make_rootfs`:

```bash
cd /path/to/directory/containing/make_rootfs
```

Make it executable if necessary:

```bash
chmod +x make_rootfs
```

Run it:

```bash
./make_rootfs
```

It then generates the `initrammfs.tar.gz`.

### Windows

Use WSL2 for the `make_rootfs` step.

From WSL2, it is preferable to copy the source tree into the Linux filesystem instead of building directly under `/mnt/c`.

For example:

```bash
cp -a /mnt/c/path/to/source ~/rx3-source
cd ~/rx3-source
```

Locate `make_rootfs`:

```bash
find . -type f -name make_rootfs
```

Then:

```bash
cd /path/to/directory/containing/make_rootfs
chmod +x make_rootfs
./make_rootfs
```
---

## Platform support

| Step | macOS | Linux | Windows |
|---|---:|---:|---:|
| Extract ZIP files | Yes | Yes | Yes |
| Reassemble split archive | Yes | Yes | Yes |
| Extract `tar.bz2` | Yes | Yes | Yes |
| Run `make_rootfs` | Yes | Yes | Via WSL2 |
| Obtain `initramfs.tar.gz` | Yes | Yes | Via WSL2 |

---

## Full process

```text
A9BEE4F7-6932-4E11-8D9F-5288F5F79EC2.zip
57CB205B-D45A-4143-BC09-22D8400074C2.zip
        │
        │ 7-Zip
        ▼
pioneerdj_xdj_rx3.tar.bz2.00
pioneerdj_xdj_rx3.tar.bz2.01
        │
        │ concatenate
        ▼
pioneerdj_xdj_rx3.tar.bz2
        │
        │ tar -xjf
        ▼
XDJ-RX3 source tree
        │
        │ make_rootfs
        │
        │ ./ltib --deploy
        ▼
initramfs.tar.gz
```