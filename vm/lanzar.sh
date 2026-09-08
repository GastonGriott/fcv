#!/bin/bash
# Lanza la corrida FCV POA in-protocol en una VM de Compute Engine.
#
#   bash vm/lanzar.sh            # crea bucket (si falta), sube codigo y arranca la VM
#   bash vm/lanzar.sh --dry-run  # imprime lo que haria, sin crear nada
#
# La VM se autoapaga al terminar (ver startup.sh). Para seguirla:
#   gcloud compute instances get-serial-port-output fcv-poa --zone=$ZONE --project=$PROJECT
set -euo pipefail

PROJECT="${PROJECT:?define PROJECT=<tu-proyecto-gcp>}"
ZONE="${ZONE:-us-central1-a}"
MACHINE="${MACHINE:-c2d-highcpu-56}"
JOBS="${JOBS:-56}"
BUCKET="${BUCKET:?define BUCKET=<tu-bucket-gcs>}"
RUN_ID="${RUN_ID:-$(date +%Y%m%d-%H%M)}"
METHODS="${METHODS:-poa,mpoa}"
DECODERS="${DECODERS:-penalty}"
SPECS="${SPECS:-default}"
# gcloud usa la coma para separar pares en --metadata, asi que va con +
METHODS_META="$(echo "$METHODS" | tr ',' '+')"
DECODERS_META="$(echo "$DECODERS" | tr ',' '+')"
VM="fcv-poa-${RUN_ID}"
REPO="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GC="${GCLOUD:-gcloud}"

DRY=0
[[ "${1:-}" == "--dry-run" ]] && DRY=1

say() { printf '\n\033[1m%s\033[0m\n' "$*"; }
run() { if [[ $DRY == 1 ]]; then echo "  [dry] $*"; else eval "$@"; fi; }

say "1. Bucket gs://${BUCKET}"
if ! "$GC" storage buckets describe "gs://${BUCKET}" --project="$PROJECT" >/dev/null 2>&1; then
  run "\"$GC\" storage buckets create gs://${BUCKET} --project=$PROJECT --location=us-central1 --uniform-bucket-level-access"
else
  echo "  ya existe"
fi

say "2. Empaquetar el codigo (solo lo que la corrida necesita)"
PKG="$(mktemp -d)/fcv_pkg.tar.gz"
run "tar czf '$PKG' -C '$REPO' fcv"
run "\"$GC\" storage cp '$PKG' gs://${BUCKET}/code/fcv_pkg.tar.gz --project=$PROJECT"

say "3. Crear la VM (recorre zonas/tipos hasta encontrar capacidad)"
# El stockout de un tipo en una zona es rutinario en GCE, no un error del plan:
# se reintenta en la siguiente combinacion en vez de abortar.
#
# TODOS los tipos de esta lista son de 32 vCPU: el proyecto tiene CPUS_ALL_REGIONS
# limitada a 32 globalmente, asi que una maquina de 44, 48 o 56 no se crea nunca.
# La lista anterior las incluia y el recorrido moria siempre en la primera de
# ellas, porque exceder la cuota no es stockout y el script aborta con razon ante
# cualquier otro error. Si algun dia se amplia la cuota, agregar tipos mas grandes
# ADELANTE de estos.
CANDIDATOS="${CANDIDATOS:-c2d-highcpu-32:us-central1-a c2d-highcpu-32:us-central1-b c2d-highcpu-32:us-central1-c n2d-highcpu-32:us-central1-a n2d-highcpu-32:us-central1-b e2-highcpu-32:us-central1-a e2-highcpu-32:us-central1-b e2-highcpu-32:us-central1-c}"

CREADA=""
for cand in $CANDIDATOS; do
  MT="${cand%%:*}"; ZN="${cand##*:}"
  NJOBS="${MT##*-}"
  VMN="fcv-poa-${RUN_ID}"
  echo "  probando ${MT} en ${ZN} (${NJOBS} jobs, metodos ${METHODS})..."
  if [[ $DRY == 1 ]]; then echo "  [dry] crearia ${VMN}"; CREADA="$VMN"; ZONE="$ZN"; MACHINE="$MT"; JOBS="$NJOBS"; break; fi
  ERR="$(mktemp)"
  if "$GC" compute instances create "${VMN}"       --project="${PROJECT}" --zone="${ZN}" --machine-type="${MT}"       --image-family=debian-12 --image-project=debian-cloud       --boot-disk-size=50GB --boot-disk-type=pd-balanced       --scopes=storage-rw       --metadata-from-file=startup-script="${REPO}/vm/startup.sh"       --metadata=bucket="${BUCKET}",jobs="${NJOBS}",run-id="${RUN_ID}",methods="${METHODS_META}",decoders="${DECODERS_META}",specs="${SPECS}"       --labels=proyecto=fcv,corrida=poa-in-protocol >"$ERR" 2>&1; then
    CREADA="$VMN"; ZONE="$ZN"; MACHINE="$MT"; JOBS="$NJOBS"
    echo "  -> creada ${VMN} (${MT}, ${ZN})"
    break
  fi
  if grep -q 'ZONE_RESOURCE_POOL_EXHAUSTED' "$ERR"; then
    echo "  sin capacidad en esta zona, siguiente"
  else
    # cualquier otro fallo NO es stockout: mostrarlo entero y abortar, porque
    # reintentar en otra zona lo repetiria identico y lo disfrazaria de capacidad
    echo "  ERROR distinto de stockout:"; sed 's/^/    /' "$ERR" | head -12
    exit 1
  fi
done

if [[ -z "$CREADA" ]]; then
  echo "NINGUNA combinacion tenia capacidad. Reintenta mas tarde o agrega tipos a CANDIDATOS." >&2
  exit 1
fi
VM="$CREADA"

cat <<EOF

Lanzada. La VM se autoapaga al terminar y deja todo en gs://${BUCKET}/${RUN_ID}/

  seguir el log:   $GC compute instances get-serial-port-output ${VM} --zone=${ZONE} --project=${PROJECT} | tail -40
  ver resultados:  $GC storage ls gs://${BUCKET}/${RUN_ID}/
  traer los CSV:   $GC storage cp 'gs://${BUCKET}/${RUN_ID}/*.csv' .
  matarla ya:      $GC compute instances delete ${VM} --zone=${ZONE} --project=${PROJECT} --quiet

  OJO: autoapagar NO es borrar. Una VM apagada no cobra CPU pero su disco sigue
  costando (~US\$2/mes por 50 GB). Bórrala cuando tengas los CSV.
EOF
