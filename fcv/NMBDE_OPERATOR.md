# El operador de probabilidad de bDE está mal, y este es el test que lo prueba

**Estado: defecto CONFIRMADO, arreglo BLOQUEADO por acceso a la fuente.**

`fcv/methods.py:_prob_estim()` implementa el *probability estimation operator* de NMBDE
atribuyéndolo a Wang et al. (2012). No lo reproduce.

## La fuente

> Ling Wang, Xiping Fu, Yunfei Mao, Muhammad Ilyas Menhas, Minrui Fei.
> *A novel modified binary differential evolution algorithm and its applications.*
> **Neurocomputing 98 (2012) 55–75.** `10.1016/j.neucom.2011.11.033`

Verificado cerrado: Unpaywall `is_oa: false`, OpenAlex `oa_status: closed`,
`any_repository_has_fulltext: false`. No hay preprint ni copia en repositorio. Se revisaron
además los 60 trabajos que lo citan según Semantic Scholar; los 12 con PDF abierto no
reproducen la ecuación (varios citan a **otro** Wang — Wang & Guo, *binary adaptive DE* —
que no es este operador).

## El test de aceptación

El resumen público de la sección *«Analysis of the probability estimation operator»* da
tres valores con **F = 0.5**, y eso alcanza para falsar una implementación sin tener el
paper completo:

> «the probability of (0,1,1), (1,0,1) and (1,1,0) with two "1" bits and one "0" bit are
> **0.2315, 0.0266 and 0.9975** respectively due to the different sampling order when F=0.5»

Contrastado contra las dos formas candidatas, con `b = 6.0` y
`y = x_r1 + F·(x_r2 − x_r3)`:

| bits | y | publicado | `_prob_estim` actual | normalizando por (1+2F) |
|---|---:|---:|---:|---:|
| (0,1,1) | 0.00 | **0.2315** | 0.0025 | 0.0474 |
| (1,0,1) | 0.50 | **0.0266** | 0.5000 | 0.5000 |
| (1,1,0) | 1.50 | **0.9975** | 1.0000 | **0.9975** ✅ |

**Qué se puede concluir, y qué no.**

1. **La implementación actual está mal.** No reproduce ninguno de los tres valores
   publicados. Eso ya no es una sospecha.
2. **La normalización por `(1+2F)` va en la dirección correcta**: reproduce `0.9975`
   exacto, donde la actual satura en `1.0000`. Es evidencia fuerte de que el operador
   escala con `F`, coherente con que el rango de `y` sea `[-F, 1+F]` y el mapeo actual no
   lo compense — la propia docstring del código dice `y ∈ [-1,2]`, que es el rango para
   **F=1**, mientras el default es **F=0.5**.
3. **Pero la fórmula completa NO se puede derivar de acá.** Los otros dos valores no los
   produce ninguna sigmoide monótona sobre `y`: `y=0` daría `0.2315` y `y=0.5` daría
   `0.0266`, o sea el valor *menor* para el `y` *mayor*. El paper lo atribuye al
   *«different sampling order»*, así que el operador tiene una pieza más que este resumen
   no revela.

## Por qué importa

Un control ejecutado por el panel de revisión —n=50, tres clases duras, 42 corridas por
variante— mostró que la constante mueve el resultado por completo:

| bDE | SRate | gap medio |
|---|---:|---:|
| implementación actual | **0.000** (0/42) | 1.43 % |
| con la normalización | **0.286** (12/42) | 0.22 % |

Con la corrección, bDE queda **por encima del piso ILS** (0.26 en la Tabla 2 del paper).
La frase del manuscrito —*«NMBDE ranks below the minimal floor, a concrete reminder that
"a metaheuristic" is not automatically competitive»*— sería entonces un artefacto de
transcripción, no un resultado, y arrastraría al ranking de Friedman y a la defensa de §10
(*«parameters are taken from the literature»*).

## Qué hace falta

El PDF de Neurocomputing 98:55–75 (accesible por biblioteca institucional). Con la
ecuación en mano:

1. Reimplementar `_prob_estim` y **verificar contra los tres valores de arriba** antes de
   correr nada.
2. Re-correr `bde` y `mbde` sobre las 81 celdas del factorial.
3. Rehacer Friedman, la CD y el ranking.
4. Reescribir o retirar la frase del manuscrito sobre NMBDE.

**Hasta entonces, ningún resultado del paper que involucre `bde` o `mbde` debe darse por
válido.**
