# AWS-Comic-Text-Reckognition
It's a school project for PSR

# Description:
The project uses Amazon Recognition for text detection.
Base "word" limit on AWS is 50, so I thought that it could be used in comics.
Pictures for detection are sent encoded in base64
Pictures must be either png, JPG or bmp
After approving picture recognition would start, first it would determine is it a comic, manga or text, letter, poster, book
If it is a comic it will try to group up text, if not it will just append everything into a single string.
