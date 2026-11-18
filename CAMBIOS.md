# CAMBIOS.md - Registro de mejoras del bot de Telegram

## 1. Resumen

El proyecto es un bot de Telegram que analiza los mensajes que te envían y detecta emoción, toxicidad, intención, nivel de ghosting y riesgo de conflicto, sugeriendo cómo responder. Se aplicaron las siguientes mejoras:

- **Detección de toxicidad híbrida**: el modelo `hate_speech` devolvía una lista de etiquetas y el código la comparaba como texto, por lo que nunca se activaba; ahora usa modelo o intención de agresión.
- **Intención por palabras completas**: la búsqueda "palabra in texto" hacía falsos positivos (ej. "mal" dentro de "normal"); ahora usa normalización sin tildes y regex raw con `\b`.
- **Comandos /start y /help**: se añadieron dos handlers de comando registrados antes del MessageHandler de texto.
- **Toxicidad con vocabulario colombiano**: se añadieron `INSULTOS_FUERTES`, `PALABRAS_AMBIGUAS` y `_contiene_insulto()` para detectar insultos colombianos que el modelo `hate_speech` no cubre.
- **Documentación y seguridad**: se eliminó el token real de Indicaciones.txt (marcador), se fijó requirements.txt a las versiones probadas y se corrigió el README.

## 2. Mejora 1 – Detección de toxicidad

### Problema

`hate_analyzer.predict().output` devuelve una **lista de etiquetas** (ej. `['hateful']` o `[]`), no un string. El código original lo comparaba con `== "hateful"`, condición que nunca se cumplía, por lo que la toxicidad nunca se detectaba por el modelo.

### Cómo se detectó

Se probaron frases ofensivas ("eres un idiota", "te voy a matar", "mierda") y neutras. El modelo devolvía `[]` siempre y sus probabilidades máximas fueron ~0.24, sin separar frases ofensivas de neutras. Por eso el modelo por sí solo no era confiable.

### Solución

Lógica híbrida en `es_toxico`: toxicidad = "si" si el modelo marca alguna etiqueta de `ETIQUETAS_TOXICAS` **o** si la intención por reglas es `"agresion"`. `calcular_riesgo` usa la misma función para decidir riesgo Alto.

### Código ANTES

```python
def calcular_riesgo(hate_result, intencion, emocion):
    # Verificar si hay hate_speech
    if hate_result.output == "hateful" or hate_result.output == "targeted":
        return "🔴 Alto"
    elif intencion in ["celos", "reclamo", "ruptura", "manipulacion", "agresion"]:
        return "🟡 Medio"
```

y en `analizar_texto`:

```python
        # Toxicidad (basada en hate_speech)
        toxicidad = "si" if hate_pred.output in ["hateful", "targeted"] else "no"
```

### Código DESPUÉS

```python
ETIQUETAS_TOXICAS = {"hateful", "targeted", "aggressive"}


def es_toxico(hate_result, intencion):
    # El modelo puede devolver una lista de etiquetas o un string (según versión).
    salida = hate_result.output
    if isinstance(salida, list):
        modelo_marca = any(e in salida for e in ETIQUETAS_TOXICAS)
    else:
        modelo_marca = any(e == salida for e in ETIQUETAS_TOXICAS)
    # Las reglas de detectar_intencion ya clasifican insultos/amenazas como "agresion".
    return modelo_marca or intencion == "agresion"
```

y `calcular_riesgo` ahora empieza así:

```python
def calcular_riesgo(hate_result, intencion, emocion):
    # Verificar si hay hate_speech. El modelo devuelve una LISTA de etiquetas
    # (no un string), por lo que la comparación original == "hateful" fallaba.
    salida = hate_result.output
    if isinstance(salida, list):
        hay_hate = any(e in salida for e in ETIQUETAS_TOXICAS)
    else:
        hay_hate = any(e == salida for e in ETIQUETAS_TOXICAS)

    if hay_hate or intencion == "agresion":
        return "🔴 Alto"
    elif intencion in ["celos", "reclamo", "ruptura", "manipulacion"]:
        return "🟡 Medio"
```

y en `analizar_texto`:

```python
        # Toxicidad (híbrida: modelo + reglas de agresion)
        toxicidad = "si" if es_toxico(hate_pred, intencion) else "no"
```

## 3. Mejora 2 – Intención por palabras completas

### Problema

La búsqueda original usaba `palabra in texto`, lo que hacía coincidir subcadenas: "mal" dentro de "normal", "solo" dentro de "solo quiero", "dejar" dentro de "dejar de fumar", generando falsos positivos de agresión, tristeza y ruptura.

### Solución

Se añadió `_normalizar` (minúsculas + eliminación de tildes con `unicodedata`) y `_contiene_palabra`, que busca cada frase como palabra/frase completa usando regex raw con `\b` (`patron = r"\b" + re.escape(...) + r"\b"`). Todas las reglas de `detectar_intencion` ahora usan `_contiene_palabra`.

### Reglas nuevas o ajustadas

- **Reclamo**: ampliado con "por que no me respondes", "no me respondes", "no me contestas", "me ignoras", "no me escribes", "por que tardas", "por que demoras", "por que no respondes", "no contestas".
- **Inseguridad**: "me da miedo perderte", "no soy suficiente", "me quieres", "tengo miedo de que", "no valgo nada", "no me quieres" (colocada antes de reclamo/tristeza).
- **Agresión**: se quitó "mal"; se añadieron amenazas físicas "te voy a matar", "te voy a destruir".
- **Ruptura**: se quitó "dejar" (genérico); se usan frases específicas ("no quiero seguir", "acabo", "se acabo", "hasta aqui", "se termino", "terminar con", "queremos terminar").
- **Tristeza**: se quitó "mal" y "solo" suelto; se usan frases específicas "me siento solo", "me siento sola", "estoy solo", "estoy sola".

### Código ANTES (ejemplo de regla)

```python
    elif any(palabra in texto for palabra in ["triste", "deprimido", "mal", "solo", "soledad", "llorar", "me siento mal"]):
        return "tristeza"
```

### Código DESPUÉS

```python
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
```

y la regla de tristeza:

```python
    # Tristeza (se quita "mal" y "solo" suelto; se usan frases específicas)
    if _contiene_palabra(texto_norm, ["triste", "deprimido", "soledad",
                                       "llorar", "me siento mal",
                                       "me siento solo", "me siento sola",
                                       "estoy solo", "estoy sola"]):
        return "tristeza"
```

## 4. Mejora 3 – Comandos /start y /help

Se añadieron dos funciones async:

- **start**: saludo corto y explica qué hace el bot (analiza el mensaje que te enviaron: emoción, toxicidad, intención, riesgo y sugiere cómo responder).
- **ayuda** (`/help`: cómo usarlo ("pega aquí el mensaje que recibiste") con 2 ejemplos: "por qué no me respondes" y "te quiero mucho".

Ambos envían texto plano sin `parse_mode` para evitar problemas con Markdown. Se registran con `CommandHandler("start", start)` y `CommandHandler("help", ayuda)` **antes** del `MessageHandler(filters.TEXT & ~filters.COMMAND, responder)` para que los comandos no pasen por el analizador de texto.

## 5. Mejora 4 – Toxicidad con vocabulario colombiano

### Problema

Probando el bot real, los insultos colombianos no se marcaban como tóxicos. El modelo `hate_speech` no cubre insultos generales y la lista de agresión era corta (solo "odio", "estupido", "idiota", "mierda", etc.).

### Cómo se detectó

Se probaron frases con insultos colombianos ("eres un hijueputa", "malparido", "pirobo", etc.) y el modelo devolvía `[]` siempre; las reglas de intención tampoco las cubrían porque no estaban en el vocabulario.

### Solución

Se añadieron dos constantes de vocabulario y una función auxiliar:

- `INSULTOS_FUERTES`: lista de insultos que cuentan solos (hijueputa, hijo de puta, malparido, pirobo, pendejo, etc.). Se permite terminación plural opcional `(?:s|es)?` antes del `\b` final, por lo que matchean también "hijueputas", "malparidos", "idiotas", etc. Para "hijo de tapa" también matchea "hijos de puta".
- `PALABRAS_AMBIGUAS`: documentadas en comentario (marica, guevon, huevon, gonorrea, chimba, parce, perra, zorra, basura, inutil). En Colombia se usan con cariño u otros contextos (perra/zorra son animales, basura es un objeto, inutil puede ser tristeza: "me siento inútil"), por eso NO cuentan solas como toxicidad.
- `_contiene_insulto(texto)`: normaliza, colapsa letras repetidas 3+ veces ("hijueputaaaa" → "hijueputa") y busca cada insulto como palabra completa con regex raw (`r"\b...\b"(?:s|es)?`).

### Cambios en `es_toxico` y `calcular_riesgo`

Ambas funciones aceptan ahora un parámetro opcional `texto=""`:

```python
def es_toxico(hate_result, intencion, texto=""):
    ...
    return modelo_marca or intencion == "agresion" or _contiene_insulto(texto)
```

```python
def calcular_riesgo(hate_result, intencion, emocion, texto=""):
    ...
    if hay_hate or intencion == "agresion" or _contiene_insulto(texto):
        return "🔴 Alto"
```

### Cambios en `detectar_intencion`

Si el texto contiene un insulto fuerte, la intención es "agresion" con prioridad sobre cualquier otra regla:

```python
    # Insultos fuertes tienen prioridad: si hay un insulto, la intención es agresión
    if _contiene_insulto(texto):
        return "agresion"
```

## 6. Documentación y seguridad

- Se reemplazó el token por un marcador en `Indicaciones.txt` (línea "se reemplazó el token por un marcador"). El token real sigue en el historial de git del repositorio original, por lo que **debe revocarse con @BotFather**.
- `requirements.txt` fijado a las versiones realmente instaladas y probadas (`python-telegram-bot==20.7`, `pysentimiento==0.7.3`, `transformers==5.22.2`, `torch==2.15.0`, `numpy==2.4.6`). Se eliminó `scikit-learn` (no se usa en el código).
- `Indicaciones.txt` conserva los pasos originales de instalación con versiones más antiguas; el entorno probado usa las versiones de `requirements.txt`.
- Se corrigió el README: se desenvelopó del bloque de código markdown, se eliminó `models/` y `LICENSE` del árbol (no existen), se eliminó `scikit-learn`, se cambió la carpeta clonada a `machine-learning-Bot-telegram`, se añadieron `pruebas.py` y `CAMBIOS.md`, y se documentó que la toxicidad es híbrida y que existen los comandos /start y /help.

## 7. Pruebas

Se creó `pruebas.py` en la raíz del repositorio (UTF-8). Al inicio inserta en `sys.modules` un módulo falso `pysentimiento` cuyo `create_analyzer` devuelve `None`, y luego hace `from predict import detectar_intencion`. No usa `exec` para recortar el archivo. Imprime una tabla frase / esperada / ANTES / DESPUÉS / OK y un resumen.

Resultado de las 10 frases:

| frase | esperada | ANTES | DESPUÉS | resultado |
|-------|----------|-------|---------|-----------|
| te quiero mucho | afecto | afecto | afecto | OK |
| por qué no me respondes | reclamo | normal | reclamo | OK |
| por que no me respondes | reclamo | normal | reclamo | OK |
| todo normal | normal | agresion | normal | OK |
| ok | desinteres | desinteres | desinteres | OK |
| estoy triste | tristeza | tristeza | tristeza | OK |
| me da miedo perderte | inseguridad | normal | inseguridad | OK |
| eres un idiota | agresion | agresion | agresion | OK |
| hablamos mañana | normal | normal | normal | OK |
| te voy a matar | agresion | normal | agresion | OK |

Total: 10 | Aprobadas: 10 | Fallas: 0 (5 de 10 acertadas antes, 10 de 10 ahora).

Casos de límite (no cuentan en el total, sin cambiar reglas):

| frase | ANTES | DESPUÉS |
|-------|-------|---------|
| solo quiero hablar contigo | tristeza | normal |
| ya llegué a casa | desinteres | desinteres |
| dejar de fumar es difícil | ruptura | normal |

Insultos colombianos (9 frases, 9/9 OK):

| frase | intención esperada | toxicidad esperada | resultado |
|-------|-------------------|-------------------|-----------|
| eres un hijueputa | agresion | sí | OK |
| malparido no me vuelvas a escribir | agresion | sí | OK |
| hijueputaaaa | agresion | sí | OK |
| que pirobo eres | agresion | sí | OK |
| te quiero mucho hijueputa | agresion | sí | OK |
| vete a la mierda | agresion | sí | OK |
| son unos hijueputas | agresion | sí | OK |
| malparidos | agresion | sí | OK |
| eres una imbecil | agresion | sí | OK |

No deben ser tóxicas (7 frases, 7/7 OK):

| frase | toxicidad esperada | resultado |
|-------|-------------------|-----------|
| te quiero mucho | no | OK |
| todo normal | no | OK |
| buenos días, cómo estás | no | OK |
| me da miedo perderte | no | OK |
| me siento inútil | no | OK |
| mi perra tuvo cachorros | no | OK |
| saqué la basura | no | OK |

Casos de límite - palabras ambiguas (no cuentan en el total, limitación conocida):

| frase | intención | toxicidad | riesgo |
|-------|-----------|-----------|--------|
| qué chimba de canción | normal | no | 🟢 Bajo |
| quihubo marica cómo vas | normal | no | 🟢 Bajo |
| esa gonorrea de gol estuvo bueno | normal | no | 🟢 Bajo |

Tabla de toxicidad (sin modelos de IA, objeto falso con atributo `output`):

| output | intención | es_toxico | riesgo | esperado |
|--------|-----------|-----------|--------|----------|
| [] | agresion | sí | 🔴 Alto | sí |
| ['hateful'] | normal | sí | 🔴 Alto | sí |
| [] | normal | no | 🟢 Bajo | no |

Resultado: `es_toxico: sí, sí, no -> coincide con lo esperado: True`.

Cómo ejecutar:

```powershell
$env:PYTHONUTF8="1"
& "C:\venvs\bot\Scripts\python.exe" pruebas.py
```

## 8. Limitaciones y trabajo futuro

- Palabras sueltas como "ya" u "ok" siguen contando como desinterés incluso en frases largas (ejemplo: "ya llegué a casa" se clasifica como desinterés).
- Las intenciones son reglas por palabras clave y no entienden contexto.
- Un diccionario no entiende contexto: por ejemplo "me siento inútil" no es una ofensa aunque contenga "inútil".
- Hay insultos que no están en la lista y variantes con letras cambiadas ("hij3puta") no se detectan.
- Palabras ambiguas como "marica", "guevon", "huevon", "gonorrea", "chimba", "parce", "perra", "zorra", "basura" e "inutil" no se marcan como tóxicas por sí solas porque en Colombia también se usan con cariño o en otros contextos; solo los insultos fuertes de `INSULTOS_FUERTES` activan toxicidad.
- El modelo de `hate_speech` no separó frases ofensivas de neutras en las pruebas (devolvía `[]` siempre, probabilidades máximas ~0.24).
- Posible mejora: entrenar un modelo propio o usar un clasificador de intención basado en ML.

## 9. Cómo ejecutar

1. Configurar la variable de entorno `TELEGRAM_TOKEN` con el token del bot (obtenido de @BotFather). Nunca compartir el token ni subirlo a repositorios públicos.
2. Ejecutar el bot:

```powershell
$env:TELEGRAM_TOKEN="PEGA_AQUI_TU_TOKEN"
python bot.py
```

3. Ejecutar las pruebas sin cargar modelos de IA:

```powershell
$env:PYTHONUTF8="1"
& "C:\venvs\bot\Scripts\python.exe" pruebas.py
```
