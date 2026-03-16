import json
from video_pipeline.assembler import assemble_video



if __name__ == "__main__":
    file_path: str = "scenes.json"
    
    with open(file_path, "r") as f:
        scenes = json.load(f)

    assemble_video(
        scenes=scenes,
        title="The fascinating world of photosynthesis",
        output_path="output.mp4"
    )
    
    