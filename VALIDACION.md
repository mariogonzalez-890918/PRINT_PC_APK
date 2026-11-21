# Validación de PRINTER-TAB 0.2.1

- 20 pruebas automatizadas aprobadas (incluye las anteriores): permisos, impresión entre dos PCs, reintentos sin duplicar, colas persistentes, contraseñas desde 4 caracteres, cambio de contraseña, validación y persistencia de logo/icono, control de acceso y configuración gráfica mediante el backend sin preguntas de terminal.
- Pruebas nuevas: publicación de impresoras locales sin código, reutilización de la PC sin duplicarla, asignación independiente de impresoras de dos PCs a dos tablets, revocación y rechazo de cambios no autorizados.
- Asignación web verificada con datos de ejemplo: desmarcar una impresora y Guardar asignación conserva la selección. Evidencia en dist/PRINTER-TAB-asignacion-0.2.1.jpg.
- EXE 0.2.1 compilado con botones Compartir impresoras y Asignar impresoras a tablets. La APK permanece en 0.2.0.
- APK con nombre PRINTER-TAB, versión 0.2.0 y código de versión 2. Paquete com.jad.print y certificado SHA-256 2176325ddc84fbb0ccd613e8a8a61ec7e9d31a85c3c0c59767a9a7ddcbdf6809 idénticos a la versión anterior. Firma v2/v3 verificada.
- Panel gráfico Windows compilado como aplicación Windows (winexe), con icono, botones, bandeja y la leyenda completa del Área de TI GMP. Revisión visual en Windows sin CMD; imagen en dist/PRINTER-TAB-panel-0.2.0.png.
- Actualización verificada instalando 0.2.0 sobre 0.1.0 en una carpeta aislada: cuenta conservada, ejecutable antiguo retirado, panel PRINTER-TAB instalado y backend nuevo reconoce la cuenta. Desinstalación de la prueba completada.

Pendiente: ejecución de la APK en tablets reales y pruebas de impresión física en los modelos de impresora utilizados. Estas validaciones no permiten prometer ausencia de fallos ni compatibilidad universal.

La cuenta por correo sigue alojada en un servidor local; no incluye hospedaje en Internet. Las claves privadas de firma, credenciales y datos de cuentas no se publican.
