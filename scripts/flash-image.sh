#!/bin/bash
#
# SD カードに Raspberry Pi OS を書き込み、初期設定を注入する
#
# Usage:
#   ./flash-image.sh [hostname]
#   VARIANT=lite ./flash-image.sh rpi-signage-02
#   IMAGE=path/to.img.xz ./flash-image.sh rpi-signage-01
#
set -euo pipefail

# ==== 設定 ====

RPI_IMAGER="/Applications/Raspberry Pi Imager.app/Contents/MacOS/rpi-imager"
OS_LIST_URL="https://downloads.raspberrypi.com/os_list_imagingutility_v3.json"

HOSTNAME="${1:-rpi-signage-01}"
USERNAME="signage"
TIMEZONE="Asia/Tokyo"
VARIANT="${VARIANT:-desktop}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SSH_PUB_KEY_FILE="$SCRIPT_DIR/../keys/signage.pub"

# ==== ヘルパー関数 ====

die()  { echo "Error: $*" >&2; exit 1; }
info() { echo "==> $*"; }

resolve_image_url() {
    local name="Raspberry Pi OS (Legacy, 64-bit)"
    [[ "$VARIANT" == "lite" ]] && name="$name Lite"

    curl -s "$OS_LIST_URL" | python3 -c "
import json, sys
def find(items):
    for item in items:
        if 'subitems' in item:
            r = find(item['subitems'])
            if r: return r
        if item.get('name') == '${name}':
            return item.get('url')
print(find(json.load(sys.stdin).get('os_list', [])) or '')
"
}

select_disk() {
    info "接続されているディスク:"
    diskutil list external physical 2>/dev/null || diskutil list
    echo ""
    read -rp "SD カードのデバイス名 (例: disk2): " disk_name
    echo "/dev/${disk_name:?デバイス名が空です}"
}

confirm_disk() {
    local disk="$1"
    diskutil info "$disk" 2>/dev/null | grep -E 'Disk Size|Device / Media Name'
    echo ""
    echo "WARNING: $disk の全データが消去されます"
    read -rp "続行？ (yes): " confirm
    [[ "$confirm" == "yes" ]] || { echo "中止"; exit 0; }
}

generate_firstrun() {
    local ssh_pub_key="$1"
    cat << EOF
#!/bin/bash
set -e
raspi-config nonint do_hostname "$HOSTNAME"
raspi-config nonint do_change_timezone "$TIMEZONE"
raspi-config nonint do_ssh 0

# セットアップウィザード無効化
rm -f /etc/xdg/autostart/piwiz.desktop

id "$USERNAME" &>/dev/null || useradd -m -s /bin/bash -G sudo,bluetooth "$USERNAME"
install -d -m 700 -o $USERNAME -g $USERNAME /home/$USERNAME/.ssh
echo '$ssh_pub_key' | install -m 600 -o $USERNAME -g $USERNAME /dev/stdin /home/$USERNAME/.ssh/authorized_keys
EOF
}

# ==== メイン ====

[[ -f "$RPI_IMAGER" ]]      || die "Raspberry Pi Imager をインストールしてください"
[[ -f "$SSH_PUB_KEY_FILE" ]] || die "SSH鍵がありません: ssh-keygen -t ed25519 -f keys/signage"

# イメージ解決
if [[ -n "${IMAGE:-}" ]]; then
    image_src="$IMAGE"
else
    info "OS リストから Bookworm arm64 ($VARIANT) を取得中..."
    image_src="$(resolve_image_url)"
    [[ -n "$image_src" ]] || die "イメージ URL が見つかりません"
fi
info "イメージ: $image_src"

# firstrun.sh 生成
firstrun="$(mktemp)"
trap 'rm -f "$firstrun"' EXIT
generate_firstrun "$(cat "$SSH_PUB_KEY_FILE")" > "$firstrun"

# SD カード選択・確認
disk="$(select_disk)"
confirm_disk "$disk"

# 書き込み
sudo "$RPI_IMAGER" --cli --first-run-script "$firstrun" "$image_src" "$disk"

echo ""
info "完了！"
echo "  ssh -i keys/signage ${USERNAME}@${HOSTNAME}.local で接続後"
echo "  ansible-playbook playbooks/site.yml を実行"
