"""Generate deterministic UR program fixtures shared by unit and system tests."""

import gzip
import pathlib
import textwrap
import typing
import xml.etree.ElementTree

RUN_SECONDS = 30.0


def program_xml(name: str, robot_directory: str = "/ursim/programs", installation_relative_path: str = "default") -> str:
    """Return a valid PolyScope 5 program that waits without moving the robot."""
    # PolyScope requires its canonical XML serialization and rejects some semantically equivalent formatting.
    template = textwrap.dedent(
        f"""
        <URProgram
          name="{name}"
          installation="default"
          installationRelativePath="{installation_relative_path}"
          directory="{robot_directory}"
          createdIn="5.14.5"
          lastSavedIn="5.14.5"
          robotSerialNumber="20195599999"
          createdInPolyscopeProgramVersion="0"
          lastSavedInPolycopeProgramVersion="2"
          crcValue="2384686873">
          <kinematics status="NOT_INITIALIZED" validChecksum="false">
            <deltaTheta value="0.0, 0.0, 0.0, 0.0, 0.0, 0.0"/>
            <a value="0.0, -0.425, -0.3922, 0.0, 0.0, 0.0"/>
            <d value="0.1625, 0.0, 0.0, 0.1333, 0.0997, 0.0996"/>
            <alpha value="1.570796327, 0.0, 0.0, 1.570796327, -1.570796327, 0.0"/>
            <jointChecksum value="-1, -1, -1, -1, -1, -1"/>
          </kinematics>
          <children>
            <InitVariablesNode/>
            <SpecialSequence type="BeforeStart">
              <children>
                <Assignment valueSource="Expression">
                  <variable name="hmi_input" prefersPersistentValue="false" favourite="false">
                    <initializeExpression/>
                  </variable>
                  <expression>
                    <ExpressionChar character="["/>
                    <ExpressionChar character="0"/>
                    <ExpressionChar character=","/>
                    <ExpressionChar character=" "/>
                    <ExpressionChar character="0"/>
                    <ExpressionChar character=","/>
                    <ExpressionChar character=" "/>
                    <ExpressionChar character="0"/>
                    <ExpressionChar character=","/>
                    <ExpressionChar character=" "/>
                    <ExpressionChar character="0"/>
                    <ExpressionChar character="]"/>
                  </expression>
                </Assignment>
                <Timer action="Start">
                  <variable name="timer_1" prefersPersistentValue="false" favourite="false">
                    <initializeExpression/>
                  </variable>
                </Timer>
              </children>
            </SpecialSequence>
            <MainProgram runOnlyOnce="false" InitVariablesNode="false">
              <children><Wait type="Sleep"><waitTime>{RUN_SECONDS}</waitTime></Wait></children></MainProgram>
          </children>
        </URProgram>
        """
    ).lstrip()
    root = xml.etree.ElementTree.fromstring(template)

    return xml.etree.ElementTree.tostring(root, encoding="unicode")


def write_program(folder: pathlib.Path, name: str, robot_directory: str = "/ursim/programs", installation_relative_path: str = "default") -> pathlib.Path:
    """Write one deterministic URP archive."""
    folder.mkdir(parents=True, exist_ok=True)
    program = folder / f"{name}.urp"
    xml = program_xml(name, robot_directory, installation_relative_path).encode("utf-8")

    with program.open("wb") as output:
        with gzip.GzipFile(fileobj=output, mode="wb", mtime=0) as archive:
            archive.write(xml)

    return program


def create_program_tree(root: pathlib.Path) -> typing.List[str]:
    """Create the complete program tree used by local, SFTP, and URSim tests."""
    write_program(root, "Main")
    production = root / "Production"
    write_program(production, "PickPart", "/ursim/programs/Production", "../default")
    ignored = root / "notes.txt"
    ignored.write_text("Not a robot program.\n", encoding="utf-8")

    return ["Main.urp", "Production/PickPart.urp"]
