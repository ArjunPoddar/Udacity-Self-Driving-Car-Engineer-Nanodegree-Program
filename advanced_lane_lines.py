import os
import numpy as np
import cv2
import pickle
import glob
import matplotlib.image as mpimg
import matplotlib.pyplot as plt
from moviepy.editor import VideoFileClip

# Declare a line class to help with the transition from one frame to another
class Line():
    def __init__(self):
        # line found in the last frame or not
        self.found = False
        # previous line fit
        self.previous_fit = None
        # radii
        self.left_curverad, self.right_curverad, self.dist_from_center = None, None, None


# Distortion Correction
def undistort_image(image, dict):
    mtx = dict["mtx"]
    dist = dict["dist"]
    image = cv2.undistort(image, mtx, dist, None, mtx)
    return image


# Sobel Correction using absolute values
def abs_sobel_thresh(img, orient = 'x', sobel_kernel = 3, thresh = (0, 255)):
    
    # Convert to grayscale
    gray = cv2.cvtColor(img, cv2.COLOR_RGB2GRAY)
    
    # Define orientation values
    if orient == 'x':
        x = 1
    elif orient == 'y':
        x = 0
    y = 1 - x
    
    # Take the derivative wrt to the orientation
    sobel = cv2.Sobel(gray, cv2.CV_64F, x, y)
    
    # Take the absolute value of the gradient
    abs_sobel = np.absolute(sobel)
    
    # Scale to 8-bit (0 - 255) then convert to type = np.uint8
    scaled_sobel = np.uint8(255*abs_sobel/np.max(abs_sobel))
    
    # Create a mask of 1 based on thresholds
    grad_binary = np.zeros_like(scaled_sobel)
    grad_binary[(scaled_sobel >= thresh[0]) & (scaled_sobel <= thresh[1])] = 1
    
    # Return the binary masked image
    return grad_binary


# Sobel correction using magnitude of x and y gradients
def mag_thresh(image, sobel_kernel = 3, thresh = (0, 255)):
    
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    
    # Take Sobel 'x' and 'y' gradients
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize = sobel_kernel)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize = sobel_kernel)
    
    # Calculate the magnitude
    magnitude = np.sqrt(sobelx**2 + sobely**2)
    
    # Scale to 8-bit (0 - 255) and convert to type = np.uint8
    scale_factor = np.max(magnitude)/255
    magnitude = (magnitude/scale_factor).astype(np.uint8)

    # Create a binary mask where mag thresholds are met
    mag_binary = np.zeros_like(magnitude)
    mag_binary[(magnitude >= thresh[0]) & (magnitude <= thresh[1])] = 1
   
    # Return the thresholded image
    return mag_binary


# Sobel correction using the angle between the x and y gradients
def dir_thresh(image, sobel_kernel=3, thresh=(0, np.pi/2)):
    
    # Convert to grayscale
    gray = cv2.cvtColor(image, cv2.COLOR_RGB2GRAY)
    
    # Take the gradient in x and y separately
    sobelx = cv2.Sobel(gray, cv2.CV_64F, 1, 0, ksize = sobel_kernel)
    sobely = cv2.Sobel(gray, cv2.CV_64F, 0, 1, ksize = sobel_kernel)
    
    # Take the absolute value of the x and y gradients
    abs_sobelx = np.absolute(sobelx)
    abs_sobely = np.absolute(sobely)
    
    # Use np.arctan2(abs_sobely, abs_sobelx) to calculate the direction of the gradient 
    direction_gradient = np.arctan2(abs_sobely, abs_sobelx)
    
    # Create a binary mask where direction thresholds are met
    dir_binary = np.zeros_like(direction_gradient)
    dir_binary[(direction_gradient >= thresh[0]) & (direction_gradient <= thresh[1])] = 1
    
    # Return direction-thresholded image    
    return dir_binary


# Thresholding using H channel (from HLS)
def hue_thresh(img, thresh=(0, 255)):
    # Convert to HLS color space
    image_hls = cv2.cvtColor(img, cv2.COLOR_RGB2HLS)
    
    # Apply a threshold to the S channel
    H = image_hls[:, :, 0]
    binary_output = np.zeros_like(H)
    binary_output[(H > thresh[0]) & (H <= thresh[1])] = 1
    
    # Return a binary image of threshold result
    return binary_output  


# Thresholding using S channel (from HLS)
def saturation_thresh(img, thresh=(0, 255)):
    # Convert to HLS color space
    image_hls = cv2.cvtColor(img, cv2.COLOR_RGB2HLS)
    
    # Apply a threshold to the S channel
    S = image_hls[:, :, 2]
    binary_output = np.zeros_like(S)
    binary_output[(S > thresh[0]) & (S <= thresh[1])] = 1
    
    # Return a binary image of threshold result
    return binary_output  


# Combine all the thresholds
def combined_thresh(img, abs_thresh = (20, 100), magnitude_thresh = (30, 100), angle_thresh = (0.7, 1.4), h_thresh = (10, 35), s_thresh = (120, 255)):
    gradx = abs_sobel_thresh(img, orient = 'x', sobel_kernel = 3, thresh = abs_thresh)
    grady = abs_sobel_thresh(img, orient = 'y', sobel_kernel = 3, thresh = abs_thresh)
    mag_binary = mag_thresh(img, sobel_kernel = 3, thresh = magnitude_thresh)
    dir_binary = dir_thresh(img, sobel_kernel = 3, thresh = angle_thresh)
    h_binary = hue_thresh(img, thresh = h_thresh)
    s_binary = saturation_thresh(img, thresh = s_thresh)
    combined_binary = np.zeros_like(gradx)
    combined_binary[(gradx == 1) & (grady ==1) & (mag_binary == 1) & (dir_binary == 1) | (h_binary == 1) & (s_binary == 1)] = 1
    return combined_binary


# Perspective transform and warping
def perspective_transform(image, source = None, destination = None):
    image_size=(image.shape[1],image.shape[0])
    
    source = np.float32(
    [[(image_size[0] / 2) - 55, image_size[1] / 2 + 100],
    [((image_size[0] / 6) - 10), image_size[1]],
    [(image_size[0] * 5 / 6) + 60, image_size[1]],
    [(image_size[0] / 2 + 55), image_size[1] / 2 + 100]])
    
    destination = np.float32(
    [[(image_size[0] / 4), 0],
    [(image_size[0] / 4), image_size[1]],
    [(image_size[0] * 3 / 4), image_size[1]],
    [(image_size[0] * 3 / 4), 0]])
    
    M = cv2.getPerspectiveTransform(source, destination)
    Minv = cv2.getPerspectiveTransform(destination, source)

    warped = cv2.warpPerspective(image, M, image_size, flags = cv2.INTER_LINEAR)
    return warped, Minv, M

# Lane Lines Detection: Sliding Window Approach
def find_lane_pixels(binary_warped):
    # Take a histogram of the bottom half of the image
    histogram = np.sum(binary_warped[binary_warped.shape[0]//2:,:], axis=0)
    
    # Create an output image to draw on and visualize the result
    out_img = np.dstack((binary_warped, binary_warped, binary_warped))*255
    
    # Find the peak of the left and right halves of the histogram
    # These will be the starting point for the left and right lines
    midpoint = np.int(histogram.shape[0]//2)
    leftx_base = np.argmax(histogram[:midpoint])
    rightx_base = np.argmax(histogram[midpoint:]) + midpoint

    # HYPERPARAMETERS
    # Choose the number of sliding windows
    nwindows = 9
    # Set the width of the windows +/- margin
    margin = 100
    # Set minimum number of pixels found to recenter window
    minpix = 50

    # Set height of windows - based on nwindows above and image shape
    window_height = np.int(binary_warped.shape[0]//nwindows)
    
    # Identify the x and y positions of all nonzero pixels in the image
    nonzero = binary_warped.nonzero()
    nonzeroy = np.array(nonzero[0])
    nonzerox = np.array(nonzero[1])
    
    # Current positions to be updated later for each window in nwindows
    leftx_current = leftx_base
    rightx_current = rightx_base

    # Create empty lists to receive left and right lane pixel indices
    left_lane_inds = []
    right_lane_inds = []

    # Step through the windows one by one
    for window in range(nwindows):
        # Identify window boundaries in x and y (and right and left)
        win_y_low = binary_warped.shape[0] - (window+1)*window_height
        win_y_high = binary_warped.shape[0] - window*window_height
        ### Find the four below boundaries of the window ###
        win_xleft_low = leftx_current - margin  # Update this
        win_xleft_high = leftx_current + margin  # Update this
        win_xright_low = rightx_current - margin  # Update this
        win_xright_high = rightx_current + margin  # Update this
        
        # Draw the windows on the visualization image
        cv2.rectangle(out_img,(win_xleft_low,win_y_low),
        (win_xleft_high,win_y_high),(0,255,0), 4) 
        cv2.rectangle(out_img,(win_xright_low,win_y_low),
        (win_xright_high,win_y_high),(0,255,0), 4) 
        
        ### Identify the nonzero pixels in x and y within the window ###
        good_left_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) & 
        (nonzerox >= win_xleft_low) &  (nonzerox < win_xleft_high)).nonzero()[0]
        good_right_inds = ((nonzeroy >= win_y_low) & (nonzeroy < win_y_high) & 
        (nonzerox >= win_xright_low) &  (nonzerox < win_xright_high)).nonzero()[0]
        
        # Append these indices to the lists
        left_lane_inds.append(good_left_inds)
        right_lane_inds.append(good_right_inds)
        
        ### If you found > minpix pixels, recenter next window ###
        ### (`right` or `leftx_current`) on their mean position ###
        if len(good_left_inds) > minpix:
            leftx_current = np.int(np.mean(nonzerox[good_left_inds]))
        if len(good_right_inds) > minpix:
            rightx_current = np.int(np.mean(nonzerox[good_right_inds]))

    # Concatenate the arrays of indices (previously was a list of lists of pixels)
    try:
        left_lane_inds = np.concatenate(left_lane_inds)
        right_lane_inds = np.concatenate(right_lane_inds)
    except ValueError:
        # Avoids an error if the above is not implemented fully
        pass

    # Extract left and right line pixel positions
    leftx = nonzerox[left_lane_inds]
    lefty = nonzeroy[left_lane_inds] 
    rightx = nonzerox[right_lane_inds]
    righty = nonzeroy[right_lane_inds]

    return leftx, lefty, rightx, righty, out_img

def fit_polynomial(binary_warped):
    # Find our lane pixels first
    leftx, lefty, rightx, righty, out_img = find_lane_pixels(binary_warped)

    ### Fit a second order polynomial to each using `np.polyfit` ###
    left_fit = np.polyfit(x = lefty, y = leftx, deg = 2)
    right_fit = np.polyfit(x = righty, y = rightx, deg = 2)

    # Generate x and y values for plotting
    ploty = np.linspace(0, binary_warped.shape[0]-1, binary_warped.shape[0] )
    try:
        left_fitx = left_fit[0]*ploty**2 + left_fit[1]*ploty + left_fit[2]
        right_fitx = right_fit[0]*ploty**2 + right_fit[1]*ploty + right_fit[2]
    except TypeError:
        
        # Avoids an error if `left` and `right_fit` are still none or incorrect
        print('The function failed to fit a line!')
        left_fitx = 1*ploty**2 + 1*ploty
        right_fitx = 1*ploty**2 + 1*ploty

    ## Visualization ##
    # Colors in the left and right lane regions
    out_img[lefty, leftx] = [255, 0, 0]
    out_img[righty, rightx] = [0, 0, 255]

    return out_img, left_fit, right_fit


def fit_poly(img_shape, leftx, lefty, rightx, righty):
    ### TO-DO: Fit a second order polynomial to each with np.polyfit() ###
    left_fit = np.polyfit(x = lefty, y = leftx, deg = 2)
    right_fit = np.polyfit(x = righty, y = rightx, deg = 2)
    # Generate x and y values for plotting
    ploty = np.linspace(0, img_shape[0]-1, img_shape[0])
    ### TO-DO: Calc both polynomials using ploty, left_fit and right_fit ###
    left_fitx = left_fit[0]*ploty**2 + left_fit[1]*ploty + left_fit[2]
    right_fitx = right_fit[0]*ploty**2 + right_fit[1]*ploty + right_fit[2]
    
    return left_fitx, right_fitx, ploty


# Lane Lines Detection: Seach from Prior 
def search_around_poly(binary_warped, left_fit, right_fit):
    # HYPERPARAMETER
    # Choose the width of the margin around the previous polynomial to search
    # The quiz grader expects 100 here, but feel free to tune on your own!
    margin = 100

    # Grab activated pixels
    nonzero = binary_warped.nonzero()
    nonzeroy = np.array(nonzero[0])
    nonzerox = np.array(nonzero[1])
    
    ### TO-DO: Set the area of search based on activated x-values ###
    ### within the +/- margin of our polynomial function ###
    ### Hint: consider the window areas for the similarly named variables ###
    ### in the previous quiz, but change the windows to our new search area ###
    left_lane_inds = ((nonzerox > (left_fit[0]*(nonzeroy**2) + left_fit[1]*nonzeroy + 
                    left_fit[2] - margin)) & (nonzerox < (left_fit[0]*(nonzeroy**2) + 
                    left_fit[1]*nonzeroy + left_fit[2] + margin)))
    right_lane_inds = ((nonzerox > (right_fit[0]*(nonzeroy**2) + right_fit[1]*nonzeroy + 
                    right_fit[2] - margin)) & (nonzerox < (right_fit[0]*(nonzeroy**2) + 
                    right_fit[1]*nonzeroy + right_fit[2] + margin)))
    
    # Again, extract left and right line pixel positions
    leftx = nonzerox[left_lane_inds]
    lefty = nonzeroy[left_lane_inds] 
    rightx = nonzerox[right_lane_inds]
    righty = nonzeroy[right_lane_inds]
    
    ### Fit a second order polynomial to each with np.polyfit() ###
    left_fit = np.polyfit(x = lefty, y = leftx, deg = 2)
    right_fit = np.polyfit(x = righty, y = rightx, deg = 2)

    # Fit new polynomials
    left_fitx, right_fitx, ploty = fit_poly(binary_warped.shape, leftx, lefty, rightx, righty)
    
    ## Visualization ##
    # Create an image to draw on and an image to show the selection window
    out_img = np.dstack((binary_warped, binary_warped, binary_warped))*255
    window_img = np.zeros_like(out_img)
    # Color in left and right line pixels
    out_img[nonzeroy[left_lane_inds], nonzerox[left_lane_inds]] = [255, 0, 0]
    out_img[nonzeroy[right_lane_inds], nonzerox[right_lane_inds]] = [0, 0, 255]

    # Generate a polygon to illustrate the search window area
    # And recast the x and y points into usable format for cv2.fillPoly()
    left_line_window1 = np.array([np.transpose(np.vstack([left_fitx-margin, ploty]))])
    left_line_window2 = np.array([np.flipud(np.transpose(np.vstack([left_fitx+margin, 
                              ploty])))])
    left_line_pts = np.hstack((left_line_window1, left_line_window2))
    right_line_window1 = np.array([np.transpose(np.vstack([right_fitx-margin, ploty]))])
    right_line_window2 = np.array([np.flipud(np.transpose(np.vstack([right_fitx+margin, 
                              ploty])))])
    right_line_pts = np.hstack((right_line_window1, right_line_window2))

    # Draw the lane onto the warped blank image
    cv2.fillPoly(window_img, np.int_([left_line_pts]), (0,255, 0))
    cv2.fillPoly(window_img, np.int_([right_line_pts]), (0,255, 0))
    result = cv2.addWeighted(out_img, 1, window_img, 0.3, 0)
    
    return result, left_fit, right_fit


# Draw Lanes on Original Image
def draw_lines_on_image(original_img, binary_img, left_fit, right_fit, Minv):
    ploty = np.linspace(0, binary_img.shape[0]-1, binary_img.shape[0])
    
    warp_zero = np.zeros_like(binary_img).astype(np.uint8)
    color_warp = np.dstack((warp_zero, warp_zero, warp_zero))
    
    left_fitx = left_fit[0]*ploty**2 + left_fit[1]*ploty + left_fit[2]
    right_fitx = right_fit[0]*ploty**2 + right_fit[1]*ploty + right_fit[2]
    
    pts_left = np.array([np.transpose(np.vstack([left_fitx, ploty]))])
    pts_right = np.array([np.flipud(np.transpose(np.vstack([right_fitx, ploty])))])
    pts = np.hstack((pts_left, pts_right))
    # Draw the lane onto the warped blank image
    cv2.fillPoly(color_warp, np.int_([pts]), (0, 255, 0))
    
    # Warp the previous image back to original image space using inverse perspective matrix (Minv)
    newwarp = cv2.warpPerspective(color_warp, Minv, (original_img.shape[1], original_img.shape[0])) 
    # Combine the result with the original image
    result = cv2.addWeighted(original_img, 1, newwarp, 0.4, 0)
    
    return result


# Measuring curvature and distance from the center
def measure_curvature_and_center(binary_warped, left_fit, right_fit):
    '''
    Calculates the curvature of polynomial functions in pixels.
    '''
    ploty = np.linspace(0, binary_warped.shape[0] - 1, num = binary_warped.shape[0])
    
    quadratic_coeff = 3e-4 # arbitrary quadratic coefficient
    # For each y position generate random x position within +/-50 pix
    # of the line base position in each case (x=200 for left, and x=900 for right)
    leftx = np.array([200 + (y**2)*quadratic_coeff + np.random.randint(-50, high=51) 
                                    for y in ploty])
    rightx = np.array([900 + (y**2)*quadratic_coeff + np.random.randint(-50, high=51) 
                                    for y in ploty])

    leftx = leftx[::-1]  # Reverse to match top-to-bottom in y
    rightx = rightx[::-1]  # Reverse to match top-to-bottom in y

    # Fit a second order polynomial to pixel positions in each fake lane line
    left_fit = np.polyfit(ploty, leftx, 2)
    right_fit = np.polyfit(ploty, rightx, 2)
    
    # Define y-value where we want radius of curvature
    # We'll choose the maximum y-value, corresponding to the bottom of the image
    y_eval = np.max(ploty)
    
    ##### Implement the calculation of R_curve (radius of curvature) #####
    left_curverad = round(
        np.power(1+((2*left_fit[0]*y_eval+left_fit[1])**2), 1.5)/(2*np.absolute(left_fit[0])),
        2)
    right_curverad = round(
        np.power(1+((2*right_fit[0]*y_eval+right_fit[1])**2), 1.5)/(2*np.absolute(right_fit[0])),
        2)
    
    # position of the vehicle with respect to center
    xm_per_pix = 3.7/700 # meters per pixel in x dimension
    height, width = binary_warped.shape
    position = width//2
    left_intercept = left_fit[0]*(height**2) + left_fit[1]*height + left_fit[2]
    right_intercept = right_fit[0]*(height**2) + right_fit[1]*height + right_fit[2]
    center = (left_intercept + right_intercept) / 2
    dist_from_center = round((position - center) * xm_per_pix, 2)
    
    return left_curverad, right_curverad, dist_from_center


# Calculate Curvature Radius
def get_curvature_radius(line, y):
    a, b, c = line
    return np.power(1 + np.square(2 * a * y + b), 3 / 2) / np.abs(2 * c)


# Calculate left and right curvature
def curvature_in_meters(binary_image,left_fit,right_fit):
    height, width = binary_image.shape
    # Define conversions in x and y from pixels space to meters
    ym_per_pix = 30/720 # meters per pixel in y dimension
    xm_per_pix = 3.7/700 # meters per pixel in x dimension
    
    ys = np.linspace(0, height - 1, height)
    left_x = left_fit[0] * (ys**2) +left_fit[1] * ys + left_fit[2]
    right_x = right_fit[0] * (ys**2) + right_fit[1] * ys + right_fit[2]
    
    left_fit_cr = np.polyfit(ys*ym_per_pix, left_x*xm_per_pix, 2)
    right_fit_cr = np.polyfit(ys*ym_per_pix, right_x*xm_per_pix, 2)
    
    # Define y-value where we want radius of curvature
    # We'll choose the maximum y-value, corresponding to the bottom of the image
    y_eval = np.max(ys)
    
    # Calculation of R_curve (radius of curvature)
    left_curverad = ((1 + (2*left_fit_cr[0]*y_eval*ym_per_pix + left_fit_cr[1])**2)**1.5) / np.absolute(2*left_fit_cr[0])
    right_curverad = ((1 + (2*right_fit_cr[0]*y_eval*ym_per_pix + right_fit_cr[1])**2)**1.5) / np.absolute(2*right_fit_cr[0])
    
    position = width//2
    left_intercept = left_fit[0]*(height**2) + left_fit[1]*height + left_fit[2]
    right_intercept = right_fit[0]*(height**2) + right_fit[1]*height + right_fit[2]
    center = (left_intercept + right_intercept) / 2
    dist_from_center = round((position - center) * xm_per_pix, 2)
    
    return left_curverad, right_curverad, dist_from_center


# Print the curve-radii and the distance on the original image
def print_data_on_image(image, left_curverad, right_curverad, dist_from_center):
    out_image = np.copy(image)
    height, width = out_image.shape[0], out_image.shape[1]
    font = cv2.FONT_HERSHEY_PLAIN
    text_left = 'Left Curve Radius: ' + '{:04.2f}'.format(left_curverad) + 'm'
    text_right = 'Right Curve Radius: ' + '{:04.2f}'.format(right_curverad) + 'm'
    cv2.putText(out_image, text_left, (40,70), font, 2, (200,255,200), 2, cv2.LINE_AA)
    cv2.putText(out_image, text_right, (40, 100), font, 2, (200,255,200), 2, cv2.LINE_AA)
    text = '{:04.3f}'.format(dist_from_center) + 'm ' + ' distance from center'
    cv2.putText(out_image, text, (40, 130), font, 2, (200,255,200), 2, cv2.LINE_AA)
    return out_image


# Design the pipeline of the image
def pipeline(image):
    # undistort the image
    undistorted = undistort_image(image, dist_pickle)
    
    # get the binary image by applying different thresholding techniques
    thresholded = combined_thresh(undistorted)
    
    # apply perspective transform
    binary_warped, Minv, M = perspective_transform(thresholded)

    # Fit lane lines
    ## If lanes are not detected in the previous frame, use sliding windows to detect lines in the current frame
    if left_line.found == False or right_line.found == False:
        lanes_detected, left_fit, right_fit = fit_polynomial(binary_warped)
    ## If lanes are detected in the previous frame, use them to detect lines in the current frame
    else:
        lanes_detected, left_fit, right_fit = search_around_poly(binary_warped, left_line.previous_fit, right_line.previous_fit)
        
    # plot the lines on the original image
    plotted_lane = draw_lines_on_image(image, binary_warped, left_fit, right_fit, Minv)

    # print the curvature radii and distance from the center on the image    
    left_curverad, right_curverad, dist_from_center = curvature_in_meters(binary_warped, left_fit, right_fit)
    printed_data_on_image = print_data_on_image(plotted_lane, left_curverad, right_curverad, dist_from_center)

    # Save the fitted lines for the next frame
    left_line.previous_fit, right_line.previous_fit = left_fit, right_fit
    left_line.found, right_line.found = True, True
    
    # return the plotted lane
    return printed_data_on_image


if __name__ == "__main__":
    images = glob.glob('data/camera_cal/calibration*.jpg')

    # Calculate calibration matrix and distortion coefficients from all the chessboard images
    objpoints = []
    imgpoints = []
    objp=np.zeros((6*9,3),np.float32)
    objp[:,:2]=np.mgrid[0:9,0:6].T.reshape(-1,2)
    nx = 9
    ny = 6
    for file in images:
        # Read an image
        image = cv2.imread(file)
        # Convert to grayscale
        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        # Find corners
        ret, corners = cv2.findChessboardCorners(gray, (nx, ny), None)
        # If corners were found then obtain the calibration matrix and distortion coefficients
        if ret == True:
            imgpoints.append(corners)
            objpoints.append(objp)
            cv2.drawChessboardCorners(image, (nx, ny), corners, ret)
            ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, gray.shape[::-1], None, None)
            undist = cv2.undistort(image, mtx, dist, None, mtx) 
        image = cv2.imread(images[5])
        image_size = (image.shape[1], image.shape[0])

    # Do camera calibration given object points and image points
    ret, mtx, dist, rvecs, tvecs = cv2.calibrateCamera(objpoints, imgpoints, image_size, None, None)
    dst = cv2.undistort(image, mtx, dist, None, mtx)

    # Save the camera calibration result for later use (we won't worry about rvecs / tvecs)
    dist_pickle = {}
    dist_pickle["mtx"] = mtx
    dist_pickle["dist"] = dist
    # pickle.dump(dist_pickle, open("data/camera_calibration.p", "wb" ))
    input_video = 'data/test_videos/project_video.mp4'
    output_video = 'data/output_videos/project_video_solution_new.mp4'
    
    # Define the left and right lines
    left_line = Line()
    right_line = Line()
    
    # Prepare the input clip
    clip1 = VideoFileClip(input_video).subclip(0, 5)
    
    # Run the lane detection pipeline on the input clip
    out_clip1 = clip1.fl_image(pipeline)


