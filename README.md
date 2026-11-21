# PRINTER-TAB · versión inicial 0.2.0

Sistema de impresión para Windows y tablets Android: una cuenta administradora identificada por correo, varias PCs con impresoras instaladas y permisos por tablet. Proyecto independiente alojado en https://github.com/mariogonzalez-890918/PRINT_PC_APK.

## Archivos para instalar

- `dist/PRINTER-TAB-Instalador-0.2.0.exe`: instalador Windows x64 por usuario; incluye Python y el motor PDF, no necesitas instalar Python.
- `dist/PRINTER-TAB-Android-0.2.0.apk`: APK firmada para Android 8 o posterior; instalación directa, fuera de Play Store.

El instalador Windows aún no tiene certificado de firma de editor. La firma Android permite instalar y actualizar con la misma clave local; no representa publicación o certificación de Google Play.

## Cómo funciona

Una PC aloja el **servidor y consola administrador**. Cada PC con impresoras ejecuta un **agente de impresión**, incluida la PC del servidor si también tiene impresoras. Desde el panel gráfico de esa PC puedes iniciar servidor e impresión juntos.

La tablet elige PC1 o PC2 y una impresora compartida. El servidor guarda el trabajo y el agente de esa PC lo recoge y entrega al controlador de Windows. Las PCs consultan al servidor; no requieren que las tablets se conecten directamente a sus impresoras ni puertos entrantes en cada agente.

El correo identifica **una cuenta local**, sin correo de verificación, recuperación por email o servicio en la nube. La dirección del servidor debe configurarse al vincular cada dispositivo. La versión inicial administra una cuenta por servidor. No es una copia de PrintHand ni utiliza su código.

## Puesta en marcha

1. Instala el EXE en cada PC Windows x64. Instala primero los controladores Epson, Bixolon u otros del fabricante y comprueba una impresión desde Windows.
2. Abre el acceso directo **PRINTER-TAB**: aparece un panel gráfico con icono, sin CMD. En la PC servidor pulsa **Crear cuenta / servidor** e introduce correo, contraseña de 4 a 200 caracteres y confirmación. No hay credenciales predeterminadas.
3. Pulsa **Abrir administración** en el panel para entrar a `http://localhost:8765` con esa cuenta. El panel puede minimizarse a la bandeja de Windows; cerrarlo con la X lo deja en la bandeja. **Salir** detiene los componentes iniciados desde ese panel.
4. Reserva una IP para esa PC en el router. Los demás dispositivos usarán, por ejemplo, `http://192.168.0.10:8765`. `localhost` solo funciona en la propia PC servidor.
5. Permite TCP 8765 entrante hacia esa PC en la red privada. Si tienes permiso para administrar Windows, puedes ejecutar en PowerShell elevado, sustituyendo el CIDR por **las subredes reales autorizadas**:

   ```powershell
   New-NetFirewallRule -DisplayName 'PRINTER-TAB - red autorizada' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -Profile Private -RemoteAddress '192.168.0.0/24','192.168.1.0/24'
   ```

   Este proyecto no ha modificado tu firewall ni tu router. No abras el puerto al Internet público. Para otra sede usa una VPN o un despliegue HTTPS administrado.
6. En la consola pulsa **Vincular PC**. En cada PC abre **PRINTER-TAB → Vincular esta PC**, introduce dirección del servidor, correo de la cuenta, código y nombre (PC1, PC2, Caja...). Pulsa **Iniciar impresión** después de vincular. El código vence en 15 minutos y se utiliza una vez. Usa nombres diferentes para distinguir las PCs.
7. Instala la APK en cada tablet habilitando la instalación desde la fuente que utilices. En la consola genera **Vincular tablet**. En la APK introduce dirección, correo, nombre y código.
8. En **Tablets y permisos**, marca las impresoras permitidas para cada tablet y pulsa **Guardar permisos**. Por defecto no tiene ninguna. Se pueden asignar impresoras de varias PCs a la misma tablet.
9. En la APK actualiza impresoras, elige PC e impresora, archivo y opciones. Confirma **Imprimir**. También puedes usar **Compartir → PRINTER-TAB** desde una aplicación que comparta un PDF, JPG o PNG.
10. Consulta el historial en la APK o la consola. El botón **Actualizar** renueva el estado. Los botones **Detener servidor** y **Detener impresión** detienen cada componente; la X minimiza a la bandeja. El instalador ofrece iniciar el agente al entrar a Windows como opción, desactivada de inicio.

## Actualizar desde 0.1.0

Cierra la versión anterior y ejecuta el nuevo EXE. Se conserva el identificador del instalador y la carpeta de datos `%LOCALAPPDATA%\JADPrint`; no se cambian automáticamente la cuenta, las contraseñas ni las vinculaciones. Los accesos directos nuevos se llaman PRINTER-TAB. El nuevo EXE es una aplicación gráfica de Windows con icono incorporado, panel y bandeja.

En Android instala la APK 0.2.0 encima de la anterior. Mantiene el paquete `com.jad.print`, la firma original y los datos de vinculación; ahora se muestra como PRINTER-TAB. No desinstales primero la APK si quieres conservar sus datos.

## Cambiar logo, icono y contraseña

En el panel pulsa **Logo / icono / contraseña**, inicia sesión como administrador y abre **Personalización**.

- **Logo:** PNG, JPG o WebP de hasta 2 MB. Se guarda en el servidor y aparece en la consola y los paneles vinculados.
- **Icono Windows:** ICO, PNG, JPG o WebP de hasta 2 MB. Se convierte a un ICO con varios tamaños y se aplica a la ventana, bandeja y accesos directos PRINTER-TAB existentes al volver al panel. Los agentes vinculados reciben la personalización del servidor. El icono incorporado al instalador/EXE en el Explorador y el icono de Android siguen siendo los de la compilación.
- Ambos tienen un botón para restaurar el original. En **Cambiar contraseña** introduce la actual, la nueva de 4 a 200 caracteres y su confirmación.

**Aplicaciones gestionadas, desarrolladas y administradas por Área de TI GMP · [sistemas@grupomipan.com](mailto:sistemas@grupomipan.com)**

## Cable y Wi-Fi en segmentos distintos

Por ejemplo, servidor en `192.168.0.10` y tablet en `192.168.1.50` pueden trabajar juntos si el router enruta entre esas redes y permite alcanzar `192.168.0.10:8765`. Una red Wi-Fi de invitados con aislamiento suele impedirlo. Compartir un correo no elimina el aislamiento de red.

Prueba primero abrir la dirección del servidor en el navegador de la tablet: debe aparecer la página de acceso. Para una PC agente puedes comprobar `Test-NetConnection 192.168.0.10 -Port 8765`. No es necesario iniciar sesión como administrador en el navegador de una tablet para imprimir.

## Formatos y opciones

- PDF, PNG y JPEG; máximo 25 MB por archivo y 25 megapíxeles por imagen.
- Entre 1 y 20 copias, ajustar al papel o tamaño real, color o monocromo, papel del controlador, A4 o Carta.
- Tickets y etiquetas: configura rollo 80/58 mm o etiqueta en el controlador de Windows y envía un **PDF de las dimensiones correctas**, con papel del controlador y tamaño real. La conversión de imagen no genera automáticamente una etiqueta de medidas exactas.
- Utiliza el controlador instalado en Windows: la marca no basta para garantizar compatibilidad. Debe probarse cada combinación de modelo, controlador y tamaño de papel. No se implementaron corte de papel, cajón de dinero, ESC/POS directo ni protocolos propietarios.
- Word, Excel y páginas web deben exportarse o compartirse como PDF. Esta versión no añade un servicio de impresión al diálogo nativo Android: se usa la APK o su destino de Compartir.
- Evita seleccionar impresoras virtuales que abran un diálogo para guardar archivos; el agente está diseñado para impresoras físicas que imprimen sin interacción.

## Estados y reintentos

- **En espera**: guardado en el servidor, aún no recogido por la PC. Puede esperar a que vuelva a conectarse.
- **Entregado a PC · sin confirmar**: el agente recibió el trabajo. Una interrupción en este punto exige revisar la PC; no se reenvía automáticamente al motor.
- **Enviado a Windows**: el motor informó entrega al controlador. No significa que salió papel; una impresora sin papel puede conservar el trabajo en su cola.
- **Error**: revisa el mensaje y la cola Windows antes de crear otro trabajo.
- **Resultado incierto**: hubo interrupción o el motor no respondió a tiempo. Revisa la cola y el documento físico antes de repetir.

Los reintentos de carga desde la APK conservan el identificador y el archivo en su almacenamiento privado, incluso al reiniciarla. El servidor rechaza reutilizar el mismo identificador para otro contenido. Una confirmación perdida no crea otra entrada. Esta protección reduce duplicados; no garantiza entrega física exactamente una vez ante fallos de hardware o del controlador.

Si un envío queda pendiente en la tablet, usa **Reintentar envío pendiente**. Si el servidor lo había aceptado, devuelve el mismo trabajo. No desvincules/reinstales la APK para resolver una confirmación perdida: perderías su identificador local. Revisa el historial primero.

Desactivar una tablet bloquea sus nuevas solicitudes. Retirar un permiso también impide entregar trabajos aún en espera. Los ya entregados al agente no se pueden recuperar; revisa la cola Windows. Desactivar una PC impide que reciba nuevos trabajos.

## Datos y operación

Configuración e historial: `%LOCALAPPDATA%\JADPrint\hub`. Vinculación del agente: `%LOCALAPPDATA%\JADPrint\agent`. Son datos del usuario Windows que ejecuta cada componente; inicia siempre con ese usuario. El desinstalador conserva los datos de la cuenta.

La contraseña se almacena con sal y PBKDF2. Los códigos son temporales y de un solo uso. Los tokens de dispositivos se verifican mediante su hash en el servidor; el agente conserva su token en la carpeta privada de su usuario. No compartas estos archivos ni la carpeta de datos. La APK desactiva el respaldo Android de sus datos.

El transporte HTTP inicial está pensado para red confiable o VPN. Un dominio HTTPS puede configurarse delante del servidor sin cambiar el protocolo de la APK. No incluye recuperación de contraseña, actualizaciones automáticas, servicio de Windows ni hospedaje público.

Los archivos se borran del servidor al recibir un resultado terminal del agente; los trabajos sin recoger o sin confirmar conservan su archivo. La cola admite 100 trabajos pendientes; el historial tiene un límite de 10 000 y depura resultados con más de 30 días al alcanzarlo. Respalda la carpeta del servidor con ambos componentes detenidos. Los trabajos cuyo resultado sea incierto no se reimprimen al recuperar un respaldo.

## Compilación y pruebas

Fuentes del servidor y agente en `pc/`; Android nativo Java en `android/`. `tools/prepare_build.py` descarga dependencias oficiales en `.build/`. `tools/build.ps1` compila la APK con SDK 35 y JDK 21 y genera el instalador con Inno Setup 6. Las rutas de JDK e Inno deben ajustarse si la máquina de compilación usa otras ubicaciones. Instala Pillow 12.0.0 en el Python embebido antes de compilar. El icono se puede regenerar con `tools/make_icon.py`. Los detalles de licencias y fuentes están en `THIRD-PARTY-NOTICES.txt`.

La clave de firma Android se guarda fuera del proyecto en `%LOCALAPPDATA%\JADPrint\signing`; consérvala para publicar actualizaciones sobre esta APK. No se incluye en los entregables.

Pruebas del protocolo y permisos: `python -m unittest discover -s tests -v`. Las pruebas usan datos temporales y agentes simulados; no envían trabajos a las impresoras reales.

Para dar esta versión por lista para operación, aún se requiere instalarla en dos PCs y una tablet reales, probar el enrutamiento entre sus redes y validar PDF/carta, ticket y etiqueta en los modelos concretos que utilices.
