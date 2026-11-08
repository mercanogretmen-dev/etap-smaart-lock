#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Pure Python Debian (.deb) Package Builder
Generates a 100% valid Unix 'ar' Debian package for Pardus ETAP without requiring dpkg-deb.
"""

import os
import sys
import time
import tarfile
import tempfile
import shutil

VERSION = "1.3.0"
PACKAGE_NAME = "tahta-kilit"
DEB_FILENAME = f"{PACKAGE_NAME}_{VERSION}_all.deb"

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CLIENT_DIR = os.path.join(BASE_DIR, "client-tahta")

def create_ar_header(filename, size, mode=0o100644):
    """Unix ar archive 60-byte member header."""
    name_field = f"{filename}/".encode("ascii").ljust(16, b" ")
    timestamp = str(int(time.time())).encode("ascii").ljust(12, b" ")
    owner_id = b"0".ljust(6, b" ")
    group_id = b"0".ljust(6, b" ")
    file_mode = oct(mode)[2:].encode("ascii").ljust(8, b" ")
    file_size = str(size).encode("ascii").ljust(10, b" ")
    end_marker = b"`\n"
    return name_field + timestamp + owner_id + group_id + file_mode + file_size + end_marker

def create_tar_gz(source_dict, output_tar_path):
    """
    Creates a tar.gz archive from a dictionary of:
    { arcname: (content_bytes, mode, is_dir) }
    """
    with tarfile.open(output_tar_path, "w:gz") as tar:
        for arcname, (data, mode, is_dir) in sorted(source_dict.items()):
            ti = tarfile.TarInfo(name=arcname)
            ti.mtime = int(time.time())
            ti.uid = 0
            ti.gid = 0
            ti.uname = "root"
            ti.gname = "root"
            ti.mode = mode
            if is_dir:
                ti.type = tarfile.DIRTYPE
                tar.addfile(ti)
            else:
                ti.type = tarfile.REGTYPE
                ti.size = len(data)
                import io
                tar.addfile(ti, io.BytesIO(data))

def build():
    print(f"[*] TAHTA KILIT Debian Paketi Uretiliyor: {DEB_FILENAME}...")
    
    # 1. DEBIAN/control
    control_content = f"""Package: {PACKAGE_NAME}
Version: {VERSION}
Section: utils
Priority: optional
Architecture: all
Depends: python3, python3-pyqt6 | python3-pyqt5, python3-qrcode, python3-pil, python3-websockets
Maintainer: Mercan Robotik <iletisim@mercanrobotik.com>
Homepage: https://github.com/mercanogretmen-dev/etap-smaart-lock
Description: Etkileşimli Tahta Kilit ve Mobil Yönetim Sistemi
 Pardus ETAP akıllı tahtalar için geliştirilmiş modern, güvenli hibrit kilit sistemi.
 Geliştirici: Mercan Robotik
""".replace("\r\n", "\n").encode("utf-8")

    # 2. DEBIAN/postinst
    postinst_content = """#!/usr/bin/env bash
set -e

# Python baytkodu derle (.pyc) ve yetkileri kısıtla
python3 -m compileall -q /opt/etap-smartlock 2>/dev/null || true
chown -R root:root /opt/etap-smartlock 2>/dev/null || true
chmod -R 777 /opt/etap-smartlock 2>/dev/null || true

# Eski çakışan autostart ve oturum kalıntılarını temizle
rm -f /etc/xdg/autostart/etap-smartlock.desktop 2>/dev/null || true
rm -f /home/*/.config/autostart/etap-smartlock.desktop 2>/dev/null || true
rm -rf /home/*/.cache/sessions/* 2>/dev/null || true
rm -f /tmp/tahta_kilit_*.lock /tmp/tahta_kilit*.lock 2>/dev/null || true

# Kalıcı ayar dosyası oluştur
mkdir -p /etc/etap-smartlock
if [ ! -f /etc/etap-smartlock/config.ini ] && [ -f /opt/etap-smartlock/config.ini.default ]; then
    cp /opt/etap-smartlock/config.ini.default /etc/etap-smartlock/config.ini
    chmod 666 /etc/etap-smartlock/config.ini 2>/dev/null || true
fi

# Çalıştırılabilir sistem komutları
chmod 755 /usr/local/bin/tahta-kilit 2>/dev/null || true
chmod 755 /usr/local/bin/tahta-kilit-guncelle 2>/dev/null || true
chmod 755 /usr/local/bin/tahta-kilit-kaldir 2>/dev/null || true

echo "✅ Tahta Kilit başarıyla sisteme kuruldu!"
exit 0
""".replace("\r\n", "\n").encode("utf-8")

    # 3. DEBIAN/prerm
    prerm_content = """#!/usr/bin/env bash
pkill -9 -f kilit_ekrani.py 2>/dev/null || true
pkill -9 -f tahta-kilit 2>/dev/null || true
rm -f /tmp/tahta_kilit_*.lock /tmp/tahta_kilit*.lock 2>/dev/null || true
exit 0
""".replace("\r\n", "\n").encode("utf-8")

    control_files = {
        "./": (b"", 0o755, True),
        "./control": (control_content, 0o644, False),
        "./postinst": (postinst_content, 0o755, False),
        "./prerm": (prerm_content, 0o755, False),
    }

    # 4. DATA dosyaları
    with open(os.path.join(CLIENT_DIR, "kilit_ekrani.py"), "rb") as f:
        kilit_py = f.read().replace(b"\r\n", b"\n")
    with open(os.path.join(CLIENT_DIR, "config.ini"), "rb") as f:
        config_ini = f.read().replace(b"\r\n", b"\n")
    with open(os.path.join(BASE_DIR, "guncelle.sh"), "rb") as f:
        guncelle_sh = f.read().replace(b"\r\n", b"\n")
    with open(os.path.join(BASE_DIR, "kaldir_pardus.sh"), "rb") as f:
        kaldir_sh = f.read().replace(b"\r\n", b"\n")

    desktop_autostart = """[Desktop Entry]
Type=Application
Name=Tahta Kilit
Comment=Etkileşimli Tahta Kilit Uygulaması (Mercan Robotik)
Exec=/usr/bin/python3 /opt/etap-smartlock/kilit_ekrani.py
Path=/opt/etap-smartlock
Icon=/opt/etap-smartlock/assets/tahta_kilit_icon.png
Terminal=false
Categories=Utility;System;
Hidden=false
NoDisplay=false
X-GNOME-Autostart-enabled=true
""".replace("\r\n", "\n").encode("utf-8")

    desktop_menu = """[Desktop Entry]
Type=Application
Name=Tahta Kilit
Comment=Etkileşimli Tahta Kilit Uygulaması (Mercan Robotik)
Exec=/usr/bin/python3 /opt/etap-smartlock/kilit_ekrani.py
Path=/opt/etap-smartlock
Icon=/opt/etap-smartlock/assets/tahta_kilit_icon.png
Terminal=false
Categories=Utility;System;
""".replace("\r\n", "\n").encode("utf-8")

    bin_tahta_kilit = """#!/usr/bin/env bash
exec /usr/bin/python3 /opt/etap-smartlock/kilit_ekrani.py "$@"
""".replace("\r\n", "\n").encode("utf-8")

    bin_tahta_guncelle = """#!/usr/bin/env bash
exec bash /opt/etap-smartlock/guncelle.sh "$@"
""".replace("\r\n", "\n").encode("utf-8")

    bin_tahta_kaldir = """#!/usr/bin/env bash
exec bash /opt/etap-smartlock/kaldir_pardus.sh "$@"
""".replace("\r\n", "\n").encode("utf-8")

    data_files = {
        "./": (b"", 0o755, True),
        "./opt/": (b"", 0o755, True),
        "./opt/etap-smartlock/": (b"", 0o755, True),
        "./opt/etap-smartlock/assets/": (b"", 0o755, True),
        "./opt/etap-smartlock/kilit_ekrani.py": (kilit_py, 0o755, False),
        "./opt/etap-smartlock/config.ini.default": (config_ini, 0o644, False),
        "./opt/etap-smartlock/guncelle.sh": (guncelle_sh, 0o755, False),
        "./opt/etap-smartlock/kaldir_pardus.sh": (kaldir_sh, 0o755, False),
        "./etc/": (b"", 0o755, True),
        "./etc/xdg/": (b"", 0o755, True),
        "./etc/xdg/autostart/": (b"", 0o755, True),
        "./etc/xdg/autostart/tahta-kilit.desktop": (desktop_autostart, 0o644, False),
        "./usr/": (b"", 0o755, True),
        "./usr/share/": (b"", 0o755, True),
        "./usr/share/applications/": (b"", 0o755, True),
        "./usr/share/applications/tahta-kilit.desktop": (desktop_menu, 0o644, False),
        "./usr/local/": (b"", 0o755, True),
        "./usr/local/bin/": (b"", 0o755, True),
        "./usr/local/bin/tahta-kilit": (bin_tahta_kilit, 0o755, False),
        "./usr/local/bin/tahta-kilit-guncelle": (bin_tahta_guncelle, 0o755, False),
        "./usr/local/bin/tahta-kilit-kaldir": (bin_tahta_kaldir, 0o755, False),
    }

    # Assets klasöründeki tüm dosyaları ekle
    assets_dir = os.path.join(CLIENT_DIR, "assets")
    if os.path.isdir(assets_dir):
        for root, _, files in os.walk(assets_dir):
            for file in files:
                fpath = os.path.join(root, file)
                rel = os.path.relpath(fpath, assets_dir).replace("\\", "/")
                with open(fpath, "rb") as af:
                    content = af.read()
                data_files[f"./opt/etap-smartlock/assets/{rel}"] = (content, 0o644, False)

    temp_dir = tempfile.mkdtemp()
    try:
        control_tar_path = os.path.join(temp_dir, "control.tar.gz")
        data_tar_path = os.path.join(temp_dir, "data.tar.gz")

        create_tar_gz(control_files, control_tar_path)
        create_tar_gz(data_files, data_tar_path)

        with open(control_tar_path, "rb") as cf:
            control_tar_bytes = cf.read()
        with open(data_tar_path, "rb") as df:
            data_tar_bytes = df.read()

        debian_binary = b"2.0\n"

        output_deb = os.path.join(BASE_DIR, DEB_FILENAME)
        with open(output_deb, "wb") as deb:
            deb.write(b"!<arch>\n")
            
            # 1. debian-binary
            deb.write(create_ar_header("debian-binary", len(debian_binary)))
            deb.write(debian_binary)
            if len(debian_binary) % 2 != 0:
                deb.write(b"\n")
                
            # 2. control.tar.gz
            deb.write(create_ar_header("control.tar.gz", len(control_tar_bytes)))
            deb.write(control_tar_bytes)
            if len(control_tar_bytes) % 2 != 0:
                deb.write(b"\n")
                
            # 3. data.tar.gz
            deb.write(create_ar_header("data.tar.gz", len(data_tar_bytes)))
            deb.write(data_tar_bytes)
            if len(data_tar_bytes) % 2 != 0:
                deb.write(b"\n")

        size_kb = os.path.getsize(output_deb) / 1024
        print(f"[OK] Debian paketi hazirlandi: {output_deb} ({size_kb:.1f} KB)")

        # Geriye dönük uyumluluk ve tek tıkla doğrudan indirme için kopyalar oluştur
        legacy_deb = os.path.join(BASE_DIR, "tahta-kilit_1.1.0_all.deb")
        generic_deb = os.path.join(BASE_DIR, "tahta-kilit.deb")
        shutil.copyfile(output_deb, legacy_deb)
        shutil.copyfile(output_deb, generic_deb)

    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)

if __name__ == "__main__":
    build()
