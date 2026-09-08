#!/usr/bin/env bash
# Vigila una corrida del FCV en GCE y emite una linea por evento.
#
# El oraculo NO es `instances list`: una VM figura RUNNING despues de haber
# terminado (la corrida del UFLP lo hizo por casi dos horas) y figura TERMINATED
# tanto si acabo bien como si murio. Los oraculos buenos son la linea `fin rc=`
# del log y los CSV en el bucket.
#
# Cubre los estados terminales, no solo el feliz: si la corrida revienta, el
# filtro tiene que decir algo. Silencio y exito no pueden verse igual.
#
# Uso: vigilar.sh <vm> [zona] [proyecto] [bucket] [intervalo_seg]
set -uo pipefail

VM="${1:?falta el nombre de la VM}"
ZONE="${2:-us-central1-a}"
PROJ="${3:-griott-sandbox}"
BUCKET="${4:-}"
INTERVALO="${5:-600}"

log_serial() {
  gcloud compute instances get-serial-port-output "$VM" \
    --zone="$ZONE" --project="$PROJ" 2>/dev/null || true
}

estado() {
  gcloud compute instances describe "$VM" --zone="$ZONE" --project="$PROJ" \
    --format='value(status)' 2>/dev/null || echo GONE
}

echo "vigilando $VM en $ZONE (poll cada ${INTERVALO}s)"

PREV=""
while true; do
  LOG="$(log_serial)"

  # Acotar PRIMERO a lo que imprime el startup-script. Sin esto el filtro pesca
  # ruido del guest agent: una fecha "05/2026" entra por [0-9]+/[0-9]+, y las
  # palabras "quota"/"Quota" salen en mensajes del sistema que no son la corrida.
  PROPIO="$(printf '%s\n' "$LOG" | grep 'command("/bin/bash")' | sed 's/.*: //')"

  # Eventos que interesan: progreso de celdas, cierre, y toda firma de fallo.
  CUR="$(printf '%s\n' "$PROPIO" | grep -oE \
    'celdas x [0-9]+ seeds|^ *[0-9]+/[0-9]+$|fin rc=[0-9]+|Traceback|ABORTA[^ ]*|MemoryError|Killed|No space left|ImportError|Quota .* exceeded' \
    | sed 's/^ *//' | sort -u || true)"

  if [ -n "$CUR" ]; then
    comm -13 <(printf '%s\n' "$PREV") <(printf '%s\n' "$CUR") 2>/dev/null | sed '/^$/d'
    PREV="$CUR"
  fi

  # Terminal 1: la corrida cerro y lo dijo.
  if printf '%s\n' "$PROPIO" | grep -q 'fin rc='; then
    RC="$(printf '%s\n' "$PROPIO" | grep -o 'fin rc=[0-9]*' | tail -1)"
    TIEMPO="$(printf '%s\n' "$PROPIO" | grep -oE 'real[[:space:]]+[0-9]+m[0-9.]+s' | tail -1)"
    echo "TERMINO: $RC   ${TIEMPO:-}"
    if [ -n "$BUCKET" ]; then
      echo "artefactos en el bucket:"
      gcloud storage ls "$BUCKET" 2>/dev/null | tail -5 || echo "  (aun no aparecen)"
    fi
    echo "RECORDATORIO: autoapagar NO es borrar. Borra la VM cuando bajes los CSV."
    exit 0
  fi

  # Terminal 2: la VM se fue sin dejar `fin rc=` -> murio, no termino.
  ST="$(estado)"
  case "$ST" in
    TERMINATED|GONE|STOPPING)
      echo "ALERTA: la VM quedo en '$ST' y el log NO tiene 'fin rc='."
      echo "        La corrida murio sin cerrar. Revisa el log serial completo."
      exit 1
      ;;
  esac

  sleep "$INTERVALO"
done
