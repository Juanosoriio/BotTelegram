# pruebas.py - Pruebas de detectar_intencion sin cargar modelos de IA
# Codificacion UTF-8
import sys
import types
import subprocess
from pathlib import Path

# Insertar modulo falso "pysentimiento" antes de importar predict
falso_pysentimiento = types.ModuleType("pysentimiento")


def create_analyzer_falso(*args, **kwargs):
    return None


falso_pysentimiento.create_analyzer = create_analyzer_falso
sys.modules["pysentimiento"] = falso_pysentimiento

from predict import detectar_intencion as detectar_intencion_despues
from predict import es_toxico, calcular_riesgo

# --- Código ANTES (rama main) ejecutado en espacio propio ---
repo_dir = Path(__file__).resolve().parent
codigo_antes = subprocess.run(
    ["git", "-C", str(repo_dir), "show", "main:predict.py"],
    capture_output=True,
).stdout.decode("utf-8")

espacio_antes = {}
exec(codigo_antes, espacio_antes)
detectar_intencion_antes = espacio_antes["detectar_intencion"]

casos = [
    ("te quiero mucho", "afecto"),
    ("por qué no me respondes", "reclamo"),
    ("por que no me respondes", "reclamo"),
    ("todo normal", "normal"),
    ("ok", "desinteres"),
    ("estoy triste", "tristeza"),
    ("me da miedo perderte", "inseguridad"),
    ("eres un idiota", "agresion"),
    ("hablamos mañana", "normal"),
    ("te voy a matar", "agresion"),
]

print("frase".ljust(30) + "esperada".ljust(14) + "ANTES".ljust(14) + "DESPUES".ljust(14) + "OK")
print("-" * 86)
fallos = 0
for frase, esperada in casos:
    antes = detectar_intencion_antes(frase)
    despues = detectar_intencion_despues(frase)
    ok = despues == esperada
    if not ok:
        fallos += 1
    print(frase.ljust(30) + esperada.ljust(14) + antes.ljust(14) + despues.ljust(14) + ("OK" if ok else "FALLA"))
print("-" * 86)
print(f"Total: {len(casos)} | Aprobadas: {len(casos) - fallos} | Fallas: {fallos}")

# Casos de límite (no cuentan en el total, sin cambiar reglas)
casos_limite = [
    ("solo quiero hablar contigo", "normal"),
    ("ya llegué a casa", "normal"),
    ("dejar de fumar es difícil", "normal"),
]

print()
print("Casos de límite (no cuentan en el total):")
print("frase".ljust(35) + "ANTES".ljust(14) + "DESPUES".ljust(14))
print("-" * 63)
for frase, esperada in casos_limite:
    antes = detectar_intencion_antes(frase)
    despues = detectar_intencion_despues(frase)
    print(frase.ljust(35) + antes.ljust(14) + despues.ljust(14))

# Tabla de toxicidad sin modelos (objeto falso con atributo output)
class ResultadoFalso:
    def __init__(self, output):
        self.output = output


print()
print("Tabla de toxicidad (sin modelos de IA):")
print("output".ljust(18) + "intencion".ljust(14) + "es_toxico".ljust(12) + "riesgo".ljust(10) + "esperado")
print("-" * 68)
pruebas_tox = [
    ([], "agresion", True),
    (["hateful"], "normal", True),
    ([], "normal", False),
]
coincide = True
for i, (output, intencion, esperado_bool) in enumerate(pruebas_tox):
    res = ResultadoFalso(output)
    tox = es_toxico(res, intencion)
    riesgo = calcular_riesgo(res, intencion, "neutral")
    tox_texto = "sí" if tox else "no"
    ok_tox = tox == esperado_bool
    if not ok_tox:
        coincide = False
    print(str(output).ljust(18) + intencion.ljust(14) + tox_texto.ljust(12) + riesgo.ljust(10) + ("sí" if esperado_bool else "no"))
print("-" * 68)
print("es_toxico: sí, sí, no -> coincide con lo esperado:", coincide)

# Tabla de insultos colombianos
print()
print("Insultos colombianos:")
print("frase".ljust(40) + "intencion esp.".ljust(15) + "intencion obt.".ljust(15) + "tox esp.".ljust(10) + "tox obt.".ljust(10) + "resultado")
print("-" * 105)
fallos_insultos = 0
insultos = [
    ("eres un hijueputa", "agresion", True),
    ("malparido no me vuelvas a escribir", "agresion", True),
    ("hijueputaaaa", "agresion", True),
    ("que pirobo eres", "agresion", True),
    ("te quiero mucho hijueputa", "agresion", True),
    ("vete a la mierda", "agresion", True),
    ("son unos hijueputas", "agresion", True),
    ("malparidos", "agresion", True),
    ("eres una imbecil", "agresion", True),
]
for frase, int_esp, tox_esp in insultos:
    int_obt = detectar_intencion_despues(frase)
    res = ResultadoFalso([])
    tox_obt = es_toxico(res, int_obt, frase)
    ok = int_obt == int_esp and tox_obt == tox_esp
    if not ok:
        fallos_insultos += 1
    print(frase.ljust(40) + int_esp.ljust(15) + int_obt.ljust(15) + ("sí" if tox_esp else "no").ljust(10) + ("sí" if tox_obt else "no").ljust(10) + ("OK" if ok else "FALLA"))
print("-" * 105)
print(f"Total: {len(insultos)} | Aprobadas: {len(insultos) - fallos_insultos} | Fallas: {fallos_insultos}")

# Frases que NO deben ser tóxicas
print()
print("No deben ser tóxicas:")
print("frase".ljust(40) + "tox esp.".ljust(10) + "tox obt.".ljust(10) + "resultado")
print("-" * 70)
fallos_no_tox = 0
no_toxicas = [
    ("te quiero mucho", False),
    ("todo normal", False),
    ("buenos días, cómo estás", False),
    ("me da miedo perderte", False),
    ("me siento inútil", False),
    ("mi perra tuvo cachorros", False),
    ("saqué la basura", False),
]
for frase, tox_esp in no_toxicas:
    int_obt = detectar_intencion_despues(frase)
    res = ResultadoFalso([])
    tox_obt = es_toxico(res, int_obt, frase)
    ok = tox_obt == tox_esp
    if not ok:
        fallos_no_tox += 1
    print(frase.ljust(40) + ("sí" if tox_esp else "no").ljust(10) + ("sí" if tox_obt else "no").ljust(10) + ("OK" if ok else "FALLA"))
print("-" * 70)
print(f"Total: {len(no_toxicas)} | Aprobadas: {len(no_toxicas) - fallos_no_tox} | Fallas: {fallos_no_tox}")

# Casos de límite con palabras ambiguas (no cuentan en el total)
print()
print("Casos de límite - palabras ambiguas (no cuentan en el total):")
print("frase".ljust(45) + "intencion".ljust(14) + "toxicidad".ljust(12) + "riesgo")
print("-" * 75)
casos_ambiguos = [
    "qué chimba de canción",
    "quihubo marica cómo vas",
    "esa gonorrea de gol estuvo bueno",
]
for frase in casos_ambiguos:
    int_obt = detectar_intencion_despues(frase)
    res = ResultadoFalso([])
    tox_obt = es_toxico(res, int_obt, frase)
    riesgo_obt = calcular_riesgo(res, int_obt, "neutral", frase)
    print(frase.ljust(45) + int_obt.ljust(14) + ("sí" if tox_obt else "no").ljust(12) + riesgo_obt)
