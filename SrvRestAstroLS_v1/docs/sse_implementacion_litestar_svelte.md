# Guía: Implementación de Server-Sent Events (SSE) con Litestar y Svelte 5

Esta guía explica cómo implementar una comunicación en tiempo real entre un backend de Python (usando el framework Litestar) y un frontend de JavaScript (usando Svelte 5 con Runes).

Nos enfocaremos en la configuración correcta para evitar el común y frustrante error: `Cross-Origin Request Blocked`.

**Conceptos Clave:**

*   **SSE (Server-Sent Events):** Es una tecnología que permite a un servidor enviar actualizaciones a un cliente de forma unidireccional. Es más simple que WebSockets y perfecto para notificaciones, actualizaciones de estado, etc. La conexión la inicia el cliente y el servidor la mantiene abierta para "empujar" datos cuando sea necesario.
*   **CORS (Cross-Origin Resource Sharing):** Es una política de seguridad del navegador que bloquea las peticiones a un dominio diferente al que sirve la página web. Si tu frontend está en `http://localhost:4321` y tu backend en `http://localhost:8000`, son orígenes diferentes, y necesitas configurar CORS en el servidor para permitir la comunicación.

---

## Parte 1: El Backend con Litestar (El Servidor que Emite)

El trabajo del backend es:
1.  Permitir explícitamente que nuestro frontend se conecte (la configuración CORS).
2.  Crear un "endpoint" o ruta que mantenga la conexión abierta.
3.  Enviar mensajes con un formato específico (`data: ...\n\n`).

### Paso 1.1: Configuración del Servidor y CORS

Esta es la parte más importante para evitar el error de `Cross-Origin`. En tu archivo principal del servidor, necesitas configurar el `CORSConfig` de Litestar.

**Ejemplo de archivo `main.py`:**

```python
# main.py
import asyncio
import json
from datetime import datetime
from litestar import Litestar, get
from litestar.config.cors import CORSConfig
from litestar.response import Stream
import uvicorn

# ---
# 1. La Configuración de CORS ---
# Esta configuración le dice al navegador "Está bien recibir peticiones desde estos orígenes".

# Para DESARROLLO (permite cualquier origen, muy cómodo para pruebas locales)
cors_config = CORSConfig(
    allow_origins=["*"],  # El "*" es un comodín que significa "cualquier origen".
    allow_methods=["GET"], # SSE solo necesita el método GET.
)

# Para PRODUCCIÓN (mucho más seguro, solo permite el dominio de tu frontend)
# cors_config = CORSConfig(
#     allow_origins=["https://mi-dominio-frontend.com"],
#     allow_methods=["GET"],
# )


# ---
# 2. El Endpoint SSE ---
# Esta función es un "generador asíncrono". Se ejecuta en un bucle
# y "produce" (yield) datos cada vez que quiere enviar un mensaje.
@get("/api/sse-stream")
async def sse_stream() -> Stream:
    # La función interna 'event_generator' es la que realmente genera los mensajes.
    async def event_generator():
        while True:
            # Simulamos que algo pasa en el servidor.
            # En una app real, aquí esperarías un evento de una base de datos,
            # una cola de mensajes, etc.
            payload = {
                "message": "Actualización del servidor",
                "timestamp": datetime.now().isoformat()
            }

            # ¡ESTE FORMATO ES OBLIGATORIO!
            # - Debe empezar con "data: "
            # - El contenido suele ser un string de JSON.
            # - Debe terminar con DOS saltos de línea "\n\n".
            sse_message = f"data: {json.dumps(payload)}\n\n"

            yield sse_message # Enviamos el mensaje al cliente.

            # Esperamos 2 segundos antes de enviar el siguiente mensaje.
            await asyncio.sleep(2)

    # Litestar usa 'Stream' para manejar respuestas que se envían a lo largo del tiempo.
    # Es crucial especificar el media_type para que el navegador entienda que es un stream SSE.
    return Stream(event_generator(), media_type="text/event-stream")


# ---
# 3. Crear la Aplicación Litestar ---
# Aquí juntamos la ruta y la configuración de CORS.
app = Litestar(
    route_handlers=[sse_stream],
    cors_config=cors_config
)

# ---
# (Opcional) Bloque para ejecutar el servidor directamente ---
if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)

```

**Para ejecutar este servidor:**
1.  Guarda el código como `main.py`.
2.  Instala las dependencias: `pip install "litestar[standard]"` y `pip install uvicorn`.
3.  Ejecuta desde tu terminal: `uvicorn main:app --reload`.

Tu servidor ahora está corriendo en `http://localhost:8000` y tiene una ruta `http://localhost:8000/api/sse-stream` lista para enviar eventos.

---

## Parte 2: El Frontend con Svelte 5 (El Cliente que Escucha)

El trabajo del frontend es:
1.  Conectarse al endpoint SSE del servidor usando la API `EventSource` del navegador.
2.  Escuchar los mensajes que llegan.
3.  Actualizar el estado de la aplicación de forma reactiva para mostrar los datos.

### Paso 2.1: El Componente Svelte

Svelte 5 introduce "Runes", una nueva forma de manejar la reactividad que es muy explícita y fácil de entender.

**Crea un nuevo componente, por ejemplo `RealTimeCard.svelte`:**

```svelte
<!-- src/components/RealTimeCard.svelte -->
<script lang="ts">
  import { $effect, $state } from 'svelte';

  // ---
  // 1. Definir el estado reactivo con Runes ---
  // $state le dice a Svelte que esta variable es "reactiva".
  // Si su valor cambia, Svelte redibujará automáticamente cualquier parte
  // de la UI que dependa de ella.
  let messages = $state<{ message: string; timestamp: string }[]>([]);
  let connectionStatus = $state<'conectando' | 'conectado' | 'error'>('conectando');

  // La URL de nuestro backend.
  const SSE_URL = 'http://localhost:8000/api/sse-stream';

  // ---
  // 2. Conectarse al servidor cuando el componente se crea ---
  // $effect es un "rune" que ejecuta código con efectos secundarios,
  // como conectarse a una API. Se ejecuta cuando el componente se monta en la página.
  $effect(() => {
    console.log('Intentando conectar al stream SSE...');

    // EventSource es la API nativa del navegador para SSE. ¡Es muy fácil de usar!
    const eventSource = new EventSource(SSE_URL);

    // Se ejecuta cuando la conexión se establece correctamente.
    eventSource.onopen = () => {
      console.log('Conexión SSE establecida.');
      connectionStatus = 'conectado';
    };

    // ¡Aquí está la magia!
    // Este evento se dispara CADA VEZ que el servidor envía un mensaje ("data: ...\n\n").
    eventSource.onmessage = (event) => {
      // event.data contiene el string JSON que envió el servidor.
      const newEventData = JSON.parse(event.data);
      
      // Actualizamos nuestro estado.
      // Como 'messages' es un $state, Svelte actualizará la lista en la UI.
      messages.unshift(newEventData); // .unshift() añade al principio del array.
      
      // Opcional: mantenemos solo los últimos 10 mensajes.
      if (messages.length > 10) {
        messages.length = 10;
      }
    };

    // Se ejecuta si hay un error en la conexión.
    eventSource.onerror = (err) => {
      console.error('Error en la conexión SSE:', err);
      connectionStatus = 'error';
      eventSource.close(); // Cerramos la conexión para evitar reintentos infinitos.
    };

    // ---
    // 3. Limpieza ---
    // La función que se retorna dentro de un $effect se ejecuta cuando
    // el componente se destruye. Es importante cerrar la conexión
    // para no dejarla abierta inútilmente.
    return () => {
      console.log('Cerrando conexión SSE.');
      eventSource.close();
    };
  });
</script>

<!-- ---
# 4. La Interfaz de Usuario (UI) ---
-->
<div class="card">
  <h2>Estado de Conexión:
    {#if connectionStatus === 'conectado'}
      <span class="status-ok">Conectado</span>
    {:else if connectionStatus === 'conectando'}
      <span class="status-pending">Conectando...</span>
    {:else}
      <span class="status-error">Error</span>
    {/if}
  </h2>

  <p>Recibiendo actualizaciones en tiempo real desde Litestar.</p>
  
  <ul class="message-list">
    {#if messages.length === 0}
      <li>Esperando el primer mensaje del servidor...</li>
    {/if}
    {#each messages as msg, i (i)}
      <li>
        <strong>{msg.message}</strong>
        <small>{new Date(msg.timestamp).toLocaleTimeString()}</small>
      </li>
    {/each}
  </ul>
</div>

<!-- Estilos para que se vea bien -->
<style>
  .card {
    border: 1px solid #ccc;
    border-radius: 8px;
    padding: 1.5rem;
    font-family: sans-serif;
    max-width: 500px;
    margin: 2rem auto;
    box-shadow: 0 2px 8px rgba(0,0,0,0.1);
  }
  .status-ok { color: green; }
  .status-pending { color: orange; }
  .status-error { color: red; }
  .message-list {
    list-style: none;
    padding: 0;
    margin-top: 1rem;
    max-height: 300px;
    overflow-y: auto;
  }
  .message-list li {
    background-color: #f5f5f5;
    padding: 0.5rem 1rem;
    border-radius: 4px;
    margin-bottom: 0.5rem;
    display: flex;
    justify-content: space-between;
    align-items: center;
  }
</style>
```

### Resumen del Flujo

1.  El usuario carga la página y el componente Svelte se monta.
2.  `$effect` se ejecuta y crea una `new EventSource()` que envía una petición `GET` a `http://localhost:8000/api/sse-stream`.
3.  El servidor Litestar recibe la petición. Como el origen (`http://localhost:4321`) está permitido por la `CORSConfig`, la acepta.
4.  El servidor ejecuta el generador `event_generator` y mantiene la conexión HTTP abierta.
5.  Cada 2 segundos, el `yield` del servidor envía un chunk de datos con el formato `data: {...}\n\n`.
6.  El navegador recibe el chunk, y el evento `onmessage` de `EventSource` se dispara en el cliente.
7.  El código Svelte parsea los datos y actualiza la variable `$state`.
8.  Svelte detecta el cambio en el estado y actualiza la lista en la pantalla.
9.  Este proceso se repite hasta que el componente se destruye o la conexión se cierra.
