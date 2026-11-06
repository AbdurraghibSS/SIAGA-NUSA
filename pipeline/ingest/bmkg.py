"""BMKG Prakiraan Cuaca per kelurahan (adm4).

Prakiraan 3 hari, interval 3 jam, diperbarui ±2× sehari, batas 60 req/menit/IP.
Setiap baris membawa `analysis_date` (waktu terbit), jadi snapshot ganda bisa
dibuang saat pembersihan. Atribusi: wajib mencantumkan BMKG sebagai sumber.
"""

from pipeline.locations import Location

SOURCE = "bmkg"
URL = "https://api.bmkg.go.id/publik/prakiraan-cuaca"


def params_for(location: Location) -> dict[str, str]:
    return {"adm4": location.adm4}
