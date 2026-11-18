# predict.py - Versión para pysentimiento 0.7.3
from pysentimiento import create_analyzer

# ─── Modelos preentrenados ─────────────────────────

print("🔄 Cargando modelos de pysentimiento...")
emotion_analyzer = create_analyzer(task="emotion", lang="es")
hate_analyzer = create_analyzer(task="hate_speech", lang="es")
print("✅ Modelos cargados correctamente")

# ─── Intención (palabras completas, sin tildes) ─────────

import re
import unicodedata


def _normalizar(texto):
    """Convierte a minúsculas y elimina tildes para comparaciones robustas."""
    texto = texto.lower()
    texto = unicodedata.normalize("NFKD", texto)
    return "".join(c for c in texto if not unicodedata.combining(c))


def _contiene_palabra(texto, palabras):
    """Busca cada frase como palabra/frase completa usando regex con \\b."""
    for palabra in palabras:
        patron = r"\b" + re.escape(_normalizar(palabra)) + r"\b"
        if re.search(patron, texto):
            return True
    return False


def _colapsar_repetidos(texto):
    """Colapsa letras repetidas 3 o más veces a una sola (ej. 'aaaa' -> 'a')."""
    return re.sub(r"(.)\1{2,}", r"\1", texto)


def _contiene_insulto(texto):
    """Devuelve True si el texto contiene un insulto fuerte como palabra completa.
    Permite terminación plural opcional (s|es) en insultos de una palabra."""
    texto_norm = _colapsar_repetidos(_normalizar(texto))
    for palabra in INSULTOS_FUERTES:
        patron = r"\b" + re.escape(_normalizar(palabra)) + r"(?:s|es)?\b"
        if re.search(patron, texto_norm):
            return True
    return False


def detectar_intencion(texto):
    texto_norm = _normalizar(texto)

    # Insultos fuertes tienen prioridad: si hay un insulto, la intención es agresión
    if _contiene_insulto(texto):
        return "agresion"

    # Afecto positivo
    if _contiene_palabra(texto_norm, ["te quiero", "te amo", "me gustas", "te extrano",
                                       "te necesito", "te adoro", "te quiero mucho"]):
        return "afecto"

    # Inseguridad (antes que reclamo/tristeza para que no la tape)
    if _contiene_palabra(texto_norm, ["me da miedo perderte", "no soy suficiente",
                                       "me quieres", "tengo miedo de que",
                                       "no valgo nada", "no me quieres"]):
        return "inseguridad"

    # Reclamos (ampliado: incluye "por qué no me respondes", "no me respondes", "no me contestas")
    if _contiene_palabra(texto_norm, ["por que no me respondes", "no me respondes",
                                       "no me contestas", "me ignoras", "no me escribes",
                                       "por que tardas", "por que demoras",
                                       "por que no respondes", "no contestas"]):
        return "reclamo"

    # Celos
    if _contiene_palabra(texto_norm, ["con quien", "quien es", "te veo con",
                                       "andabas con", "quien te escribio",
                                       "quien te habla"]):
        return "celos"

    # Agresión (se quita "mal" para evitar falsos positivos como "normal";
    # se añaden amenazas físicas)
    if _contiene_palabra(texto_norm, ["odio", "estupido", "estupida", "idiota",
                                       "imbrecil", "mierda", "que asco",
                                       "te voy a matar", "te voy a destruir",
                                       "sinverguenza", "porqueria"]):
        return "agresion"

    # Ruptura (se quita "dejar" por ser genérico; se usan frases específicas)
    if _contiene_palabra(texto_norm, ["no quiero seguir", "acabo", "se acabo",
                                       "hasta aqui", "se termino", "terminar con",
                                       "queremos terminar"]):
        return "ruptura"

    # Manipulación
    if _contiene_palabra(texto_norm, ["si me quisieras", "deberias", "nunca haces",
                                       "siempre igual", "como siempre",
                                       "si realmente me quisieras"]):
        return "manipulacion"

    # Control ("qué haces" va aquí, no en curiosidad; se decide así porque
    # en contexto de control pregunta qué estás haciendo en tiempo real)
    if _contiene_palabra(texto_norm, ["donde estas", "que haces", "con quien hablas",
                                       "dime la verdad", "ubicacion", "envia ubicacion"]):
        return "control"

    # Desinterés
    if _contiene_palabra(texto_norm, ["ok", "vale", "ah", "ya", "como digas",
                                       "da igual", "me da igual", "jaja", "jeje",
                                       "ok ok"]):
        return "desinteres"

    # Curiosidad (se quita "qué haces" porque ya se usó en control)
    if _contiene_palabra(texto_norm, ["que tal", "como estas", "como te va",
                                       "en que andas", "que cuentas"]):
        return "curiosidad"

    # Tristeza (se quita "mal" y "solo" suelto; se usan frases específicas)
    if _contiene_palabra(texto_norm, ["triste", "deprimido", "soledad",
                                       "llorar", "me siento mal",
                                       "me siento solo", "me siento sola",
                                       "estoy solo", "estoy sola"]):
        return "tristeza"

    return "normal"

# ─── Ghosting ─────────────────────────────────────────

def calcular_ghosting(texto, intencion, emocion):
    score = 0
    texto = texto.lower()
    
    # Mensajes muy cortos
    if len(texto) <= 5:
        score += 35
    
    # Respuesta de una palabra
    if len(texto.split()) == 1:
        score += 25
    
    # Palabras que indican desinterés
    if any(palabra in texto for palabra in ["ok", "vale", "ah", "ya", "luego", "ocupado", "ahora no", "después", "mañana", "ahora no puedo"]):
        score += 30
    
    # Intención relacionada
    if intencion == "desinteres":
        score += 35
    elif intencion == "reclamo":
        score += 15
    elif intencion == "afecto":
        score -= 25
    
    # Emoción negativa
    if emocion in ["sadness", "anger", "fear", "disgust"]:
        score += 10
    elif emocion in ["joy", "surprise"]:
        score -= 15
    
    return max(0, min(score, 95))

# ─── Calcular riesgo ───────────────────────────────────

def calcular_riesgo(hate_result, intencion, emocion, texto=""):
    # Verificar si hay hate_speech. El modelo devuelve una LISTA de etiquetas
    # (no un string), por lo que la comparación original == "hateful" fallaba.
    salida = hate_result.output
    if isinstance(salida, list):
        hay_hate = any(e in salida for e in ETIQUETAS_TOXICAS)
    else:
        hay_hate = any(e == salida for e in ETIQUETAS_TOXICAS)

    if hay_hate or intencion == "agresion" or _contiene_insulto(texto):
        return "🔴 Alto"
    elif intencion in ["celos", "reclamo", "ruptura", "manipulacion"]:
        return "🟡 Medio"
    elif emocion in ["anger", "disgust"]:
        return "🟡 Medio"
    else:
        return "🟢 Bajo"

# ─── Mapear emociones ───────────────────────────────────

def mapear_emocion(emocion_raw):
    emocion_map = {
        'joy': 'positivo',
        'sadness': 'tristeza',
        'anger': 'enojo',
        'surprise': 'sorpresa',
        'disgust': 'disgusto',
        'fear': 'miedo',
        'neutral': 'neutral'
    }
    return emocion_map.get(emocion_raw, 'neutral')

# ─── Toxicidad (híbrida: modelo + reglas) ─────────────────

# El modelo hate_speech de pysentimiento 0.7.3 devuelve en .output UNA LISTA
# de etiquetas (ej: ['hateful'] o []), no un string. Además, en pruebas con
# frases claramente ofensivas ("eres un idiota", "te voy a matar", "mierda")
# el modelo nunca añade etiqueta alguna; las probabilidades son muy bajas
# (max 0.24) y no separan frases ofensivas de neutras.
# Por eso usamos una lógica híbrida:
#   - Si el modelo marca alguna etiqueta -> toxicidad "si"
#   - Si la intención por reglas es "agresion" (insultos/amenazas) -> también "si"
# Esto cubre el caso en que el modelo falle pero las reglas detectan ofensas.

ETIQUETAS_TOXICAS = {"hateful", "targeted", "aggressive"}

# Vocabulario de insultos en español (minúsculas, sin tildes).
# Se listan formas masculinas y femeninas donde aplica.
INSULTOS_FUERTES = [
    "hijueputa", "hijo de puta", "jueputa", "hdp",
    "malparido", "malparida", "pirobo",
    "careverga", "care verga", "carechimba", "care chimba",
    "pendejo", "pendeja", "gilipollas", "imbecil",
    "idiota", "estupido", "estupida", "maldito", "maldita",
    "puta", "mamon", "lambon",
    "vete a la mierda", "hijo de perra",
]

# PALABRAS_AMBIGUAS: en Colombia también se usan con cariño u otros contextos,
# por eso NO cuentan solas como toxicidad.
# marica, guevon, huevon, gonorrea, chimba, parce (coloquialismo cariñoso)
# perra, zorra (también son animales); basura (objeto); inutil (puede ser tristeza: "me siento inútil")
PALABRAS_AMBIGUAS = ["marica", "guevon", "huevon", "gonorrea", "chimba", "parce",
                     "perra", "zorra", "basura", "inutil"]


def es_toxico(hate_result, intencion, texto=""):
    # El modelo puede devolver una lista de etiquetas o un string (según versión).
    salida = hate_result.output
    if isinstance(salida, list):
        modelo_marca = any(e in salida for e in ETIQUETAS_TOXICAS)
    else:
        modelo_marca = any(e == salida for e in ETIQUETAS_TOXICAS)
    # Las reglas de detectar_intencion ya clasifican insultos/amenazas como "agresion".
    # Además, se revisa el vocabulario de insultos fuertes en español.
    return modelo_marca or intencion == "agresion" or _contiene_insulto(texto)


# ─── Función principal ─────────────────────────────────

def analizar_texto(texto):
    try:
        # 🔥 MODELOS IA con pysentimiento
        emocion_pred = emotion_analyzer.predict(texto)
        hate_pred = hate_analyzer.predict(texto)

        # Obtener emoción principal
        emocion_raw = emocion_pred.output
        emocion = mapear_emocion(emocion_raw)

        # Intención (reglas)
        intencion = detectar_intencion(texto)

        # Toxicidad (híbrida: modelo + reglas de agresion + insultos colombianos)
        toxicidad = "si" if es_toxico(hate_pred, intencion, texto) else "no"

        # Ghosting
        ghosting = calcular_ghosting(texto, intencion, emocion_raw)

        # Riesgo
        riesgo = calcular_riesgo(hate_pred, intencion, emocion_raw, texto)

        # Confianza
        confianza = max(emocion_pred.probas.values())

        return emocion, toxicidad, ghosting, riesgo, intencion, int(confianza * 100)

    except Exception as e:
        print(f"Error en analizar_texto: {e}")
        return "neutral", "no", 0, "🟢 Bajo", "normal", 50