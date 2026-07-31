from __future__ import annotations

from sqlalchemy import select

from loa_api.database import SessionLocal
from loa_api.models import BudgetRecord


# Nomes recompostos exclusivamente a partir das linhas consecutivas do Quadro 5
# do PDF 2019_volume1.pdf. A página indicada é a página física do arquivo.
VALIDATED_NAMES = {
    "26230": ("Fundação Universidade Federal do Vale do São Francisco", 133),
    "26255": ("Universidade Federal dos Vales do Jequitinhonha e Mucuri", 140),
    "26256": ("Centro Federal de Educação Tecnológica Celso Suckow da Fonseca", 141),
    "26257": ("Centro Federal de Educação Tecnológica de Minas Gerais", 141),
    "26284": ("Fundação Universidade Federal de Ciências da Saúde de Porto Alegre", 148),
    "26290": (
        "Instituto Nacional de Estudos e Pesquisas Educacionais Anísio Teixeira",
        149,
    ),
    "26291": ("Fundação Coordenação de Aperfeiçoamento de Pessoal de Nível Superior", 149),
    "26359": ("Complexo Hospitalar e de Saúde da Universidade Federal da Bahia", 151),
    "26367": ("Hospital Universitário da Universidade Federal de Juiz de Fora", 152),
    "26368": ("Hospital das Clínicas da Universidade Federal de Minas Gerais", 152),
    "26373": ("Hospital das Clínicas da Universidade Federal de Pernambuco", 153),
    "26374": (
        "Complexo Hospitalar e de Saúde da Universidade Federal do Rio Grande do Norte",
        153,
    ),
    "26378": (
        "Complexo Hospitalar e de Saúde da Universidade Federal do Rio de Janeiro",
        153,
    ),
    "26385": ("Hospital Universitário da Universidade Federal da Grande Dourados", 153),
    "26386": ("Hospital Universitário Prof. Polydoro Ernani de São Thiago", 154),
    "26389": ("Hospital de Clínicas da Universidade Federal do Triângulo Mineiro", 154),
    "26394": ("Hospital Universitário da Fundação Universidade do Maranhão", 155),
    "26396": ("Hospital de Clínicas da Universidade Federal de Uberlândia", 155),
    "26398": ("Hospital das Clínicas da Fundação Universidade Federal de Pelotas", 156),
    "26399": ("Hospital Universitário da Fundação Universidade Federal do Piauí", 156),
    "26400": ("Hospital Universitário da Fundação Universidade Federal de Sergipe", 156),
    "26442": (
        "Universidade da Integração Internacional da Lusofonia Afro-Brasileira",
        165,
    ),
    "26451": ("Hospital Universitário da Universidade Federal do Vale do São Francisco", 167),
}


def main() -> None:
    updated = 0
    with SessionLocal() as db:
        for code, (validated_name, _source_page) in VALIDATED_NAMES.items():
            records = db.execute(
                select(BudgetRecord).where(
                    BudgetRecord.organization_code == code,
                    BudgetRecord.parent_organization_code == "26000",
                )
            ).scalars()
            for record in records:
                previous_name = record.organization_name
                if previous_name == validated_name:
                    continue
                record.organization_name = validated_name
                if previous_name and previous_name in record.source_text:
                    record.source_text = record.source_text.replace(
                        previous_name, validated_name, 1
                    )
                updated += 1
        db.commit()
    print(f"Registros anuais com nome completado: {updated}")


if __name__ == "__main__":
    main()
