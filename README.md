# PRINTER-TAB 0.3.0

Aplicaciones gestionadas, desarrolladas y administradas por **Área de TI GMP · [sistemas@grupomipan.com](mailto:sistemas@grupomipan.com)**.

Servidor central de administración, agentes Windows y APK Android. El correo identifica la cuenta; cada PC, tablet o celular se une mediante un **código de registro completo PT3...**, de un solo uso y con vigencia de 15 minutos. Los clientes no necesitan escribir la IP.

## Descargar e instalar

Los archivos están en [Releases](https://github.com/mariogonzalez-890918/PRINT_PC_APK/releases):

- **PRINTER-TAB-Instalador-0.3.0.exe**: Windows x64. Incluye Python, las librerías, panel gráfico, icono y motor de impresión. No requiere instalar Python o Docker por separado. Se instala en las PCs cliente y, si se utiliza una PC Windows como servidor, en ella también.
- **PRINTER-TAB-Android-0.3.0.apk**: Android 8 o posterior para tablets y celulares. Se instala encima de la APK anterior con la misma firma y el paquete `com.jad.print` para conservar la vinculación.

El instalador Windows todavía no tiene certificado de firma de editor. La APK está firmada para instalación directa, fuera de Play Store. La versión es inicial y requiere validar la impresión física en los modelos concretos de impresora.

## Servidor, red y datos móviles

El servidor conserva la cuenta, registro de equipos, permisos, cola de documentos e inventarios. Las impresoras permanecen conectadas a sus PCs. El EXE de cada PC consulta al servidor y entrega los trabajos al controlador de Windows mediante conexiones salientes.

Funciona con una dirección del servidor que sea accesible desde los equipos:

- **Red local:** IP del servidor y TCP 8765 permitido entre las redes Wi-Fi/cableadas.
- **ZeroTier, Radmin u otra VPN:** IP de la red virtual y rutas/firewall que permitan TCP 8765. La VPN debe incluir al dispositivo y permitir comunicación con la PC servidor.
- **Datos móviles sin VPN:** servidor público por HTTPS. No hace falta comprar un dominio propio; un alojamiento puede entregar su propia dirección HTTPS. Un servidor que solo tenga IP privada necesita publicación, enrutamiento o un servicio intermedio para ser accesible desde Internet.

El código de registro incluye la dirección de conexión configurada por el administrador. No es una redirección por correo ni atraviesa por sí solo NAT, firewalls o redes aisladas. El alojamiento público no viene contratado ni activado en esta entrega.

## Preparar la cuenta y registrar los equipos

1. En la PC que será servidor abre el acceso directo **PRINTER-TAB**, pulsa **Crear servidor (TI)** y crea la cuenta por correo. Contraseña de 4 a 200 caracteres. No hay credenciales predeterminadas.
2. Mantén el panel abierto e inicia el servidor. La X minimiza a la bandeja; **Salir** detiene los componentes iniciados desde ese panel.
3. Pulsa **Abrir administración** e inicia sesión. En **Servicio central y registro** configura una vez la dirección accesible del servicio, si se usará una dirección pública o una IP VPN específica. Vacío utiliza las direcciones locales detectadas. No escribas `localhost` como dirección destinada a otros equipos.
4. Genera un código con **Registrar PC** o **Registrar móvil** y copia el código PT3 completo. Cada equipo necesita un código distinto.
5. En una PC cliente pulsa **Unir con código**, introduce el correo, el código completo y su nombre. En Android introduce correo, nombre y código completo. No se solicita la IP en estos formularios.
6. En cada PC con impresoras instala antes su controlador de Windows y pulsa **Compartir impresoras**. Inicia su agente de impresión. El servidor, si también tiene impresoras, debe registrarse como una PC con su propio código de PC.
7. En la consola, dentro de cada PC, decide cuáles impresoras quedan habilitadas para compartir. Después, en **Asignar impresoras a PCs y móviles**, marca las que puede utilizar cada equipo y guarda. Los permisos se comprueban en el servidor.
8. La APK permite elegir PC e impresora y enviar un PDF, PNG o JPEG; también aparece como destino de Compartir. El EXE tiene **Imprimir archivo** para enviar documentos a impresoras de otra PC. Cada equipo ve únicamente sus impresoras autorizadas.

No es necesario dar la contraseña administradora a cada cliente: se unen con correo y código. Un cliente nuevo comienza sin permisos de impresión. Desactivar una PC, dispositivo o la compartición de una impresora impide nuevos trabajos autorizados por esa condición. Los trabajos ya entregados al controlador requieren revisar la cola Windows.

## Auditoría de PCs, tablets y celulares

En **Inventario / Excel** del EXE o en **Auditoría de equipos** de la consola:

- **Solicitar auditoría** envía una solicitud al equipo registrado. Una PC la atiende con su agente activo; un móvil la atiende cuando la APK está abierta, conectada y desocupada.
- Windows consulta mediante instrucciones fijas y de solo lectura: fabricante/modelo, sistema, CPU, RAM, discos, placa base y gráficos. Los datos no disponibles se registran como errores de consulta.
- Android reporta fabricante/modelo, sistema, CPU/ABI, procesadores, RAM, almacenamiento interno y pantalla. Las restricciones de Android limitan el acceso a números de serie y otros detalles de hardware. No se piden permisos adicionales para acceder a esos identificadores.
- La APK incluye **Enviar inventario del equipo** para generar un reporte manual.
- **Descargar Excel** exporta las hojas Equipos y Componentes, con fecha de recepción y estado de solicitud. Las celdas recibidas de los equipos se guardan como texto cuando corresponde para evitar ejecución de fórmulas.

Los inventarios solo son consultables/exportables por el administrador de esa cuenta. Son datos reportados por los agentes, no una certificación independiente del hardware. No se implementó escritorio remoto ni ejecución arbitraria de comandos desde el servidor.

## Impresión y confirmaciones

PDF, PNG y JPEG, hasta 25 MB. Imágenes hasta 25 megapíxeles; 1 a 20 copias. En Android: ajustar al papel o tamaño real, papel del controlador/A4/Carta y color/monocromo. El envío inicial desde PC usa ajuste al papel y el papel del controlador.

Para tickets o etiquetas configura el rollo/tamaño en el controlador de Windows y genera un PDF de las medidas correctas. No incluye corte de papel, cajón de dinero, ESC/POS directo ni formatos propietarios. Word/Excel deben exportarse a PDF.

**Enviado a Windows** confirma entrega al controlador, no salida física de papel. **Sin confirmar** o **Resultado incierto** exige revisar la cola antes de volver a imprimir. Los reintentos de la APK y del EXE conservan el identificador y el archivo pendiente para no crear otro trabajo si se perdió la respuesta del servidor. No garantiza entrega física exactamente una vez ante fallos del controlador o del hardware.

## Personalización y actualizaciones

Desde **Logo / icono / contraseña** puedes cambiar/restaurar logo e icono de Windows y cambiar contraseña. PNG/JPG/WebP hasta 2 MB; el icono también admite ICO. El icono personalizado se aplica al panel, bandeja y accesos directos existentes; el del instalador/EXE en Explorador y el de Android son los incorporados en la compilación.

Cierra la versión anterior con **Salir** antes de actualizar el EXE. Datos Windows: `%LOCALAPPDATA%\JADPrint`. Se conserva esa ruta para mantener cuentas, colas, permisos y vinculaciones de versiones anteriores. Los códigos antiguos simples siguen siendo compatibles en los clientes que ya conservan una dirección; para nuevas instalaciones genera códigos PT3 con el servidor 0.3.0.

## Alojamiento opcional del servidor

Las PCs y móviles solo necesitan sus instaladores. Si se elige un alojamiento Python administrado, el código incluye `pc/central_server.py`, `requirements-server.txt` y una plantilla opcional `render.yaml`. Esa plantilla utiliza almacenamiento persistente y puede generar cargos; no se ha aplicado ni contratado un servicio.

En un alojamiento Python configura:

- `PRINTER_TAB_DATA`: ruta persistente de la base de datos y la cola.
- `PRINTER_TAB_ADMIN_EMAIL` y `PRINTER_TAB_ADMIN_PASSWORD` (o `PRINTER_TAB_ADMIN_PASSWORD_FILE`): solo crean la cuenta en la primera instalación; no cambian una cuenta existente. Guarda la contraseña como secreto del alojamiento.
- `PORT`: puerto interno del servicio, predeterminado 8765.
- `PRINTER_TAB_PUBLIC_URL`: dirección pública HTTPS, cuando no la proporcione automáticamente el alojamiento. Render entrega `RENDER_EXTERNAL_URL`, que se utiliza para los códigos si no hay una dirección guardada en la consola.

La entrada de inicio es `python pc/central_server.py`. Usa almacenamiento persistente: las bases de datos y archivos de la cola no deben perderse al reiniciar/publicar. La versión administra una cuenta por servidor y no implementa verificación ni recuperación por correo. La impresión por Internet y las rutas VPN reales deben probarse en el despliegue elegido.

## Desarrollo y pruebas

Servidor/agente en `pc/`; Android nativo en `android/`; panel Windows en `tools/Launcher.cs`. `tools/build.ps1` genera ambos instaladores; `-WindowsOnly` omite recompilar Android. Runtime incluido: Python 3.13.9, Pillow 12.0.0 y openpyxl 3.1.5. Compilación Android con JDK 21 y SDK 35; Windows con .NET Framework e Inno Setup 6. Las rutas pueden ajustarse en el script.

Pruebas: `python -m unittest discover -s tests -v` con las dependencias de `requirements-server.txt`. Usan datos temporales y no imprimen en equipos reales. Clave Android fuera del repositorio: `%LOCALAPPDATA%\JADPrint\signing`; consérvala para futuras actualizaciones. No se publican claves, contraseñas, inventarios reales ni datos de cuentas.
