<script lang="ts">
  import { onMount } from 'svelte';
  import { URL_REST } from '../global.js';
  import { authFetch } from './transport.js';
  import ReconciliarApp from '../agui/ReconciliarApp.svelte';

  type User = { id: string; email: string; role: string; active?: boolean };
  let user = $state<User | null>(null);
  let checking = $state(true);
  let busy = $state(false);
  let message = $state('');
  let email = $state('');
  let password = $state('');
  let users = $state<User[]>([]);
  let newEmail = $state('');
  let newPassword = $state('');
  let newRole = $state('CONSULTA');
  let currentPassword = $state('');
  let nextPassword = $state('');
  let recoveryToken = $state('');
  let recoveryPassword = $state('');
  let adminRecoveryPassword = $state('');
  let issuedToken = $state('');

  async function api(path: string, data?: object) {
    return authFetch(`${URL_REST}/api/auth/${path}`, data === undefined ? {} : {
      method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(data)
    });
  }
  async function refresh() {
    try {
      const response = await api('me');
      user = response.ok ? await response.json() : null;
    } catch { message = 'No se pudo conectar con el servidor.'; }
    checking = false;
  }
  onMount(() => {
    refresh();
    const expired = () => { user = null; users = []; issuedToken = ''; adminRecoveryPassword = ''; message = 'Sesión finalizada. Ingrese nuevamente.'; };
    const denied = () => { message = 'No tiene permiso o la verificación CSRF fue rechazada.'; };
    window.addEventListener('concilia-session-expired', expired);
    window.addEventListener('concilia-permission-denied', denied);
    return () => {
      window.removeEventListener('concilia-session-expired', expired);
      window.removeEventListener('concilia-permission-denied', denied);
    };
  });
  async function login(event: SubmitEvent) {
    event.preventDefault(); busy = true; message = '';
    try {
      const response = await api('login', { email, password });
      if (response.ok) { user = await response.json(); message = ''; }
      else message = 'Credenciales inválidas o demasiados intentos.';
    } catch { message = 'Servidor no disponible.'; }
    finally { password = ''; busy = false; }
  }
  async function logout() {
    try {
      const response = await api('logout', {});
      if (response.ok) { user = null; users = []; issuedToken = ''; adminRecoveryPassword = ''; }
      else message = 'No se pudo cerrar la sesión; no se considera invalidada.';
    } catch { message = 'No se pudo cerrar la sesión.'; }
  }
  async function loadUsers() {
    const response = await api('users');
    if (response.ok) users = await response.json();
  }
  async function createUser(event: SubmitEvent) {
    event.preventDefault(); busy = true;
    try {
      const response = await api('users', { email: newEmail, password: newPassword, role: newRole });
      message = response.ok ? 'Usuario creado.' : 'No se pudo crear el usuario.';
      if (response.ok) await loadUsers();
    } catch { message = 'Servidor no disponible.'; }
    finally { newPassword = ''; busy = false; }
  }
  async function updateUser(target: User) {
    const response = await api(`users/${target.id}/update`, { role: target.role, active: target.active });
    message = response.ok ? 'Usuario actualizado; sus sesiones anteriores fueron revocadas si cambió el acceso.' : 'Actualización rechazada.';
    await refresh();
    if (user?.role === 'ADMINISTRADOR') await loadUsers();
  }
  async function revokeUser(target: User) {
    const response = await api(`users/${target.id}/revoke`, {});
    message = response.ok ? 'Sesiones revocadas.' : 'Revocación rechazada.';
    await refresh();
  }
  async function issueRecovery(target: User) {
    issuedToken = '';
    try {
      const response = await api(`users/${target.id}/password-reset`, { current_password: adminRecoveryPassword });
      if (response.ok) { issuedToken = (await response.json()).reset_token; message = 'Entregue el código por un canal privado verificado. Caduca en 15 minutos; no lo envíe por URL.'; }
      else message = 'Restablecimiento rechazado.';
    } catch { message = 'Servidor no disponible.'; }
    finally { adminRecoveryPassword = ''; }
  }
  async function recoverPassword(event: SubmitEvent) {
    event.preventDefault(); busy = true;
    try {
      const response = await api('password-reset', { reset_token: recoveryToken, new_password: recoveryPassword });
      message = response.ok ? 'Contraseña restablecida. Ingrese nuevamente.' : 'Código inválido, vencido o contraseña no permitida.';
    } catch { message = 'Servidor no disponible.'; }
    finally { recoveryToken = ''; recoveryPassword = ''; busy = false; }
  }
  async function changePassword(event: SubmitEvent) {
    event.preventDefault(); busy = true;
    try {
      const response = await api('password', { current_password: currentPassword, new_password: nextPassword });
      if (response.ok) { user = null; users = []; message = 'Contraseña cambiada. Ingrese nuevamente.'; }
      else message = 'Cambio de contraseña rechazado.';
    } catch { message = 'Servidor no disponible.'; }
    finally { currentPassword = ''; nextPassword = ''; busy = false; }
  }
</script>

{#if message}<p role="status" class="alert my-2">{message}</p>{/if}
{#if checking}
  <p role="status">Verificando sesión…</p>
{:else if !user}
  <form onsubmit={login} class="card border p-6 max-w-md mx-auto gap-3">
    <h2 class="text-xl">Ingresar a Concilia FCE</h2>
    <label>Correo <input class="input" type="email" autocomplete="username" bind:value={email} required /></label>
    <label>Contraseña <input class="input" type="password" autocomplete="current-password" bind:value={password} required maxlength="1024" /></label>
    <button class="btn btn-primary" disabled={busy}>Ingresar</button>
  </form>
  <details class="my-4 max-w-md mx-auto">
    <summary>Restablecer contraseña con código de recuperación</summary>
    <form onsubmit={recoverPassword} class="flex flex-col gap-3 p-3">
      <label>Código de recuperación <input class="input" type="password" autocomplete="off" bind:value={recoveryToken} required /></label>
      <label>Nueva contraseña de recuperación <input class="input" type="password" autocomplete="new-password" bind:value={recoveryPassword} required minlength="12" maxlength="1024" /></label>
      <button class="btn" disabled={busy}>Restablecer contraseña</button>
    </form>
  </details>
{:else}
  <header class="flex gap-4 items-center my-4">
    <span>{user.email} · {user.role}</span>
    <button class="btn" onclick={logout}>Cerrar sesión</button>
  </header>
  <details class="my-4">
    <summary>Cambiar contraseña</summary>
    <form onsubmit={changePassword} class="flex flex-wrap gap-3 p-3">
      <label>Contraseña actual <input class="input" type="password" autocomplete="current-password" bind:value={currentPassword} required /></label>
      <label>Nueva contraseña <input class="input" type="password" autocomplete="new-password" bind:value={nextPassword} required minlength="12" maxlength="1024" /></label>
      <button class="btn" disabled={busy}>Cambiar contraseña</button>
    </form>
  </details>
  {#if user.role === 'ADMINISTRADOR'}
    <details class="my-4">
      <summary>Administración de usuarios</summary>
      <button class="btn" onclick={loadUsers}>Listar usuarios</button>
      <label>Su contraseña para autorizar recuperación <input class="input" type="password" autocomplete="current-password" bind:value={adminRecoveryPassword} /></label>
      {#if issuedToken}
        <label>Código privado, uso único <input class="input" type="text" autocomplete="off" readonly value={issuedToken} /></label>
        <button class="btn" onclick={() => { issuedToken = ''; }}>Descartar código</button>
      {/if}
      {#each users as target (target.id)}
        <div class="flex flex-wrap gap-2 p-2">
          <span>{target.email}</span>
          <select class="select" aria-label={`Rol de ${target.email}`} bind:value={target.role}>
            <option>CONSULTA</option><option>OPERADOR</option><option>ADMINISTRADOR</option>
          </select>
          <label><input type="checkbox" bind:checked={target.active} /> Activo</label>
          <button class="btn" onclick={() => updateUser(target)}>Guardar</button>
          <button class="btn" onclick={() => revokeUser(target)}>Revocar sesiones</button>
          <button class="btn" disabled={!adminRecoveryPassword} onclick={() => issueRecovery(target)}>Generar recuperación</button>
        </div>
      {/each}
      <form onsubmit={createUser} class="flex flex-wrap gap-3 p-3">
        <label>Correo nuevo <input class="input" type="email" autocomplete="off" bind:value={newEmail} required /></label>
        <label>Contraseña inicial <input class="input" type="password" autocomplete="new-password" bind:value={newPassword} required minlength="12" maxlength="1024" /></label>
        <select class="select" aria-label="Rol nuevo" bind:value={newRole}>
          <option>CONSULTA</option><option>OPERADOR</option><option>ADMINISTRADOR</option>
        </select>
        <button class="btn" disabled={busy}>Crear usuario</button>
      </form>
    </details>
  {/if}
  <ReconciliarApp role={user.role} />
{/if}
