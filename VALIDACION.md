# Validación de JAD Print 0.1.0

- 12 pruebas automatizadas aprobadas: permisos por tablet, selección entre dos PCs, códigos de un uso, aislamiento de archivos, reintentos concurrentes, persistencia de trabajos y tratamiento de tiempo agotado del motor.
- APK compilada con SDK 35, mínimo Android 8; firma v2/v3 verificada con apksigner.
- Instalador Windows compilado con Inno Setup; instalación y desinstalación verificadas en una carpeta aislada. Se comprobó la carga del servidor, el agente y Pillow desde el runtime instalado.
- Consola verificada en navegador: acceso con una cuenta de prueba y guardado de permisos. La captura dist/consola-demo.jpg utiliza datos de ejemplo.
- Consulta de impresoras Windows verificada sin imprimir documentos reales.

Pendiente: instalación y ejecución de la APK en tablets reales, comunicación entre las subredes concretas y pruebas de impresión física en cada modelo/controlador. Estas comprobaciones no permiten prometer ausencia de fallos ni compatibilidad universal.

La cuenta identificada por correo reside en el servidor local. Esta entrega no incluye hospedaje en Internet ni descubrimiento de servidor únicamente mediante el correo.

Los instaladores listos para usar están en dist/. Las claves de firma, contraseñas, bases de datos y archivos temporales de compilación no se publican.
