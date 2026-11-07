#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)"
cd "$project_dir"

sudo pacman --config "$project_dir/pacman-official.conf" -Sy --needed \
  qemu-desktop edk2-ovmf swtpm libvirt virt-install virt-manager virt-viewer \
  dnsmasq iptables-nft spice-gtk tcpdump tk python cmake qt6-base qt6-declarative libsodium

sudo systemctl enable --now virtqemud.service virtnetworkd.service
sudo usermod -aG libvirt "$USER"

printf '%s\n' "Host dependencies installed. Log out and back in so the libvirt group applies."
printf '%s\n' "Then run: ./sandboxctl.py doctor"
