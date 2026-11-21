# Validación de PRINTER-TAB 0.3.0

- 29 pruebas automatizadas aprobadas: registro por correo/código PT3, uso único, correspondencia de correo y rol, URL central configurada por administrador, impresión de PC a PC, aislamiento por equipo, compartición global de impresoras, reintentos sin duplicar trabajos, revocación y confirmación de guardado después del commit, auditorías de Windows y Android, acceso administrativo al inventario, reporte por equipo y exportación a Excel sin fórmulas ejecutables procedentes de datos recibidos.
- APK compilada con SDK 35, mínimo Android 8, versión 0.3.0 y versionCode 3. Paquete com.jad.print y certificado SHA-256 2176325ddc84fbb0ccd613e8a8a61ec7e9d31a85c3c0c59767a9a7ddcbdf6809 conservados. Verificación de firma v2/v3 y comprobación de que el DEX incluye registro PT3 e inventario.
- EXE de Windows compilado como winexe con Python, Pillow y openpyxl incluidos. Los clientes no requieren instalar Python ni Docker.
- Consulta de componentes Windows probada en modo lectura, sin imprimir ni enviar el inventario real a servicios externos.
- Consola de auditoría verificada con datos de ejemplo de Windows y Android. Descarga real del Excel verificada: hojas Equipos y Componentes, tres equipos y cuatro filas de propiedades de componentes. Captura en dist/PRINTER-TAB-auditoria-0.3.0.jpg.
- Pruebas previas de actualización 0.1.0 a 0.2.0 conservaron la cuenta y retiraron el ejecutable anterior. La migración de esquema 0.3.0 conserva tablas y añade las de auditoría/compartición; la persistencia se verifica en pruebas temporales.

Pendiente: ejecutar la APK en dispositivos reales, probar impresión física y los caminos reales de LAN/VPN. La publicación de un servidor accesible desde datos móviles sin VPN NO está activada: requiere alojamiento o acceso público configurado. No exige comprar un dominio propio; los códigos incorporan la dirección del servicio que configure el administrador.

El proyecto incluye una plantilla opcional de alojamiento Python; no se contrató ni desplegó ningún servicio. El inventario es reportado por los agentes, con los campos que permita cada sistema. No se publican claves, contraseñas ni inventarios reales.
