#!/bin/bash
# startup-script de la VM de corrida FCV — POA in-protocol.
# Lo ejecuta Compute Engine como root al arrancar. Todo lo que imprime queda en
# la serial console y en /var/log/syslog, y se sube a GCS al terminar.
#
# Contrato: la VM se AUTOAPAGA al terminar (exito o error). Sin eso, una corrida
# que falle a los 3 minutos sigue facturando hasta que alguien se acuerde.
set -uo pipefail

BUCKET="$(curl -s -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/attributes/bucket)"
JOBS="$(curl -s -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/attributes/jobs)"
RUN_ID="$(curl -s -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/attributes/run-id)"
# metodos a correr, separados por coma. Default: la corrida de POA.
METHODS="$(curl -s -H 'Metadata-Flavor: Google' \
  http://metadata.google.internal/computeMetadata/v1/instance/attributes/methods || true)"
[ -z "${METHODS}" ] && METHODS="poa,mpoa"
METHODS="$(echo "${METHODS}" | tr '+' ',')"   # el lanzador lo manda con + (ver lanzar.sh)
TAG="$(echo "${METHODS}" | tr ',' '_')"
# decoders a correr. Default penalty, que es como se corrio todo hasta el 2026-09-07.
# Hasta esa fecha este parametro NO existia, y por eso §5 del paper se midio con un
# solo decoder pese a que §6 demuestra que el decoder decide el veredicto.
DECODERS="$(curl -s -H 'Metadata-Flavor: Google'   http://metadata.google.internal/computeMetadata/v1/instance/attributes/decoders || true)"
[ -z "${DECODERS}" ] && DECODERS="penalty"
DECODERS="$(echo "${DECODERS}" | tr '+' ',')"
TAG="${TAG}_$(echo "${DECODERS}" | tr ',' '_')"
# conjunto de instancias: "default" (135 generadas) u "orlib" (benchmark real)
SPECS="$(curl -s -H 'Metadata-Flavor: Google'   http://metadata.google.internal/computeMetadata/v1/instance/attributes/specs || true)"
[ -z "${SPECS}" ] && SPECS="default"
TAG="${TAG}_${SPECS}"

WORK=/opt/fcv
LOG=/var/log/fcv-run.log
exec > >(tee -a "$LOG") 2>&1

echo "=== FCV run ${RUN_ID} (${METHODS}) — inicio $(date -Is) ==="
echo "bucket=${BUCKET} jobs=${JOBS} metodos=${METHODS} decoders=${DECODERS} specs=${SPECS} nproc=$(nproc)"

finish() {
  local rc=$1
  echo "=== fin rc=${rc} $(date -Is) ==="
  gsutil -q cp "$LOG" "gs://${BUCKET}/${RUN_ID}/fcv-run.log" || true
  gsutil -q -m cp "${WORK}"/fcv_v2_*.csv "gs://${BUCKET}/${RUN_ID}/" || true
  gsutil -q -m rsync -r "${WORK}/_cache_${TAG}" "gs://${BUCKET}/${RUN_ID}/_cache_${TAG}" || true
  echo "resultados en gs://${BUCKET}/${RUN_ID}/"
  # autoapagado: la VM deja de facturar sola
  shutdown -h now
}
trap 'finish $?' EXIT

apt-get update -qq
apt-get install -y -qq python3 python3-venv >/dev/null

mkdir -p "$WORK" && cd "$WORK"
gsutil -q cp "gs://${BUCKET}/code/fcv_pkg.tar.gz" . || { echo "FALLO: no se pudo bajar el codigo"; exit 1; }
tar xzf fcv_pkg.tar.gz
python3 -c "import sys; print('python', sys.version)"

export FCV_CACHE_V2="${WORK}/_cache_${TAG}"
mkdir -p "$FCV_CACHE_V2"

# Pre-vuelo: el motor de busqueda es stdlib puro, pero RESOLVER un techo exacto
# necesita scipy, que aca no esta instalado a proposito. Los techos vienen
# precalculados en fcv/data_orlib/_optima.json dentro del paquete. Si a alguna
# instancia le falta el suyo, la corrida moriria recien al construirla, con horas
# de CPU ya gastadas y facturadas. Se comprueba antes de arrancar.
export FCV_SPECS="${SPECS}"
echo "--- pre-vuelo: techos del conjunto '${SPECS}' ---"
if ! python3 - <<'PREEOF'
import sys, json, os
sys.path.insert(0, "/opt/fcv")
from fcv import run_v2, exact
specs = run_v2.SPEC_SETS[os.environ["FCV_SPECS"]]()
faltan = [s[1] for s in specs
          if s[0] in ("scp_orlib", "uflp_orlib") and exact.provenance(s[1]) is None]
if faltan:
    print(f"FALLO: sin techo precalculado para {faltan}.")
    print("       Corre `preparar_orlib.py` en local y vuelve a subir el paquete:")
    print("       resolverlo aca exigiria scipy, que la VM no instala.")
    sys.exit(1)
print(f"  {len(specs)} instancias, todas con techo exacto en el cache")
PREEOF
then
  echo "FALLO en el pre-vuelo: no se arranca la corrida"; exit 1
fi

# Sincroniza el cache a GCS cada 10 min: si la VM muere, la corrida se reanuda
# desde donde iba en vez de empezar de cero.
( while true; do sleep 600
    gsutil -q -m rsync -r "$FCV_CACHE_V2" "gs://${BUCKET}/${RUN_ID}/_cache_${TAG}" || true
  done ) &

echo "--- lanzando run_v2 (metodos: ${METHODS} | decoders: ${DECODERS}) ---"
time python3 - <<PYEOF
import sys, os
sys.path.insert(0, os.environ.get("FCV_PKG", "/opt/fcv"))
from fcv import run_v2
metodos = tuple("${METHODS}".split(","))
specs = run_v2.SPEC_SETS["${SPECS}"]()
decoders = tuple("${DECODERS}".split(","))
run_v2.run(jobs=${JOBS},
           specs=specs,
           decoders=decoders,
           methods_list=metodos,
           out_prefix=os.path.join("/opt/fcv", "fcv_v2_${TAG}"))
PYEOF
echo "--- run_v2 termino ---"
ls -la "${WORK}"/fcv_v2_*.csv || echo "SIN CSV DE SALIDA"
