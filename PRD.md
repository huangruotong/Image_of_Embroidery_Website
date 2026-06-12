# Product Requirements Document

Embroidery Design Website

## Document Purpose

This document explains what embroidery design website is, who it serves, which problems it addresses, and which capabilities are already delivered in the current codebase.

## Product Overview

Embroidery Design is a web application designed to convert images into embroidery files. After registering and logging in, users can access a workspace to upload images, select pattern generation modes, adjust parameters, and view previews before exporting the designs into common embroidery machine formats.

## Problem to Be solve

- Converting images to embroidery requires professional software and complex operations.

- Single file formats cannot satisfy various embroidery machine brands.

- Users are unable to preview the final result before the physical embroidery is produced.

- The purpose of ‘Embroidery design website’ is to integrate these fragmented behaviors into one continuous workflow.

## User Analysis

### 4.1 Target users

#### 4.11 Person one: Hobbyists

Unfamiliar with professional embroidery machines. Seeking a easy tool to create embroidery from simple images.

#### 4.12 Person Tow: Beginners

Requires simple operations and the ability to preview embroidery results.

#### 4.13 Person three: small-scale sellers

Requires small-batch, cost-cost embroidery production and pays more attention to embroidery parameters and export formats.

## Current Implemented Scope

- Based on the current repository code, and in line with the personas, public evidence, and design logic above, the following capabilities already exist:

- Authentication: User registration, login, logout, and session management.

- Basic Validation: Required fields check, minimum password length and email uniqueness verification.

- Workspace Access Control: Preview and export functions are restricted to authenticated users.

- Image Upload Validation: Supports JPG, PNG, and BMP; file size limit is 5MB; invalid file are intercepted.

- Embroidery Modes: Supports three generation modes: Line, Canny, and Raster.

- Export Options: Export preview as PNG and support for four embroidery formats: PES, DST, JEF, and EXP.

- Export Safety Checks: Prevents exports for empty patterns or excessive stitch counts, returning specific error messages.

## Core User Flows

- Register -> Login -> Enter Workspace.

- Workspace -> Upload Image -> Select Mode -> Preview -> Export.

- Upload -> Select Mode -> Adjust Parameters (Iterative) -> Preview Validation -> Export.
