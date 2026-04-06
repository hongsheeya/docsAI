def video_analysis_model():
    struct = wiz.model("struct")
    return struct.video_analysis


def prototype_info():
    data = video_analysis_model().prototype_info()
    wiz.response.status(200, **data)
