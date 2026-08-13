# Shown on console/SSH login: how to return to the SSS2 kiosk.
# Installed to /etc/profile.d/sss2-kiosk-hint.sh by scripts/setup-appliance.sh.
if [ -t 1 ]; then
  printf '\n\033[1;32m╔════════════════════════════════════════════════╗\033[0m\n'
  printf '\033[1;32m║\033[0m  SSS2 appliance console                         \033[1;32m║\033[0m\n'
  printf '\033[1;32m║\033[0m  Type \033[1;36mkiosk\033[0m to return to the touchscreen UI.    \033[1;32m║\033[0m\n'
  printf '\033[1;32m║\033[0m  Update:  \033[1;36m./scripts/update-prod.sh\033[0m  (in repo)   \033[1;32m║\033[0m\n'
  printf '\033[1;32m╚════════════════════════════════════════════════╝\033[0m\n\n'
fi
