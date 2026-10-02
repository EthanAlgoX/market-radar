#!/usr/bin/env bash
cd "$(dirname "$0")"
./start.sh
radar_exit=$?
if [ "$radar_exit" -ne 0 ]; then
  echo '启动失败。按回车关闭窗口。'
  read -r
fi
exit "$radar_exit"
