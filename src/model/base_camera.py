from abc import ABC, abstractmethod


class BaseCamera(ABC):

    @abstractmethod
    def open(self) -> None:
        #Open / initialise the camera
        pass


    @abstractmethod
    def close(self) -> None:
        #Release the camera
        pass


    @abstractmethod
    def grab_frame(self): # return array/matrix 2d
        #Return latest grayscale frame with shape(H,W)
        pass
