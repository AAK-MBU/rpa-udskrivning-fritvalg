"""
This module contains functions to interact with the EDI portal.
These functions should be moved to mbu_dev_shared_components/solteqtand/application/edi_portal.py
"""

import locale
import re
import time
from contextlib import suppress
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

import pyodbc
import uiautomation as auto


def wait_for_control(
    control_type, search_params, search_depth=1, timeout=30, retry_interval=0.5
):
    """
    Waits for a given control type to become available with the specified search parameters.

    Args:
        control_type: The type of control, e.g., auto.WindowControl, auto.ButtonControl, etc.
        search_params (dict): Search parameters used to identify the control.
                            The keys must match the properties used in the control type, e.g., 'AutomationId', 'Name'.
        search_depth (int): How deep to search in the user interface.
        timeout (int): Maximum time to wait for the control, in seconds.
        retry_interval (float): Time to wait between retries, in seconds.

    Returns:
        Control: The control object if found, otherwise raises TimeoutError.

    Raises:
        TimeoutError: If the control is not found within the timeout period.
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            print(f"Searching for control: {search_params} at depth {search_depth}")
            control = control_type(searchDepth=search_depth, **search_params)
            print(f"Control found: {control}")
            print(f"Control exists: {control.Exists(0, 0)}")
            if control.Exists(0, 0):
                print(f"Control found: {search_params}")
                return control
        except Exception as e:  # pylint: disable=broad-except
            print(f"Error while searching for control: {e}")

        time.sleep(retry_interval)
        print(f"Retrying to find control: {search_params}...")

    print(f"Timeout reached while searching for control: {search_params}")
    raise TimeoutError(
        f"Control with parameters {search_params} was not found within the {timeout} second timeout."
    )


def wait_for_control_to_disappear(
    control_type, search_params, search_depth=1, timeout=30
):
    """
    Waits for a given control type to disappear with the specified search parameters.

    Args:
        control_type: The type of control, e.g., auto.WindowControl, auto.ButtonControl, etc.
        search_params (dict): Search parameters used to identify the control.
                            The keys must match the properties used in the control type, e.g., 'AutomationId', 'Name'.
        search_depth (int): How deep to search in the user interface.
        timeout (int): How long to wait, in seconds.

    Returns:
        bool: True if the control disappeared within the timeout period, otherwise False.
    """
    end_time = time.time() + timeout
    while time.time() < end_time:
        try:
            control = control_type(searchDepth=search_depth, **search_params)
            if not control.Exists(0, 0):
                return True
        except Exception as e:  # pylint: disable=broad-except
            print(f"Error while searching for control: {e}")

        time.sleep(0.5)
        print(f"Retrying to find control: {search_params}...")

    raise TimeoutError(
        f"Control with parameters {search_params} did not disappear within the timeout period."
    )


def edi_portal_check_contractor_id(
    extern_clinic_data: dict, sleep_time: int = 5
) -> dict:
    """
    Checks if the contractor ID is valid in the EDI portal.

    Args:
        extern_clinic_data (dict): A dictionary containing the contractor ID and phone number.
        sleep_time (int): Time to wait after clicking the next button.

    Returns:
        dict: A dictionary containing the row count and whether the phone number matches.
    """
    try:
        # Handle Hasle Torv Clinic special case
        if (
            extern_clinic_data[0]["contractorId"] == "477052"
            or extern_clinic_data[0]["contractorId"] == "470678"
        ):
            contractor_id = "485055"
            clinic_phone_number = "86135240"
        else:
            contractor_id = extern_clinic_data[0]["contractorId"]
            clinic_phone_number = extern_clinic_data[0]["phoneNumber"]

        edi_portal_click_next_button(sleep_time=3)

        root_web_area = wait_for_control(
            auto.DocumentControl, {"AutomationId": "RootWebArea"}, search_depth=30
        )

        class_options = [
            "form-control filter_search",
            "form-control filter_search valid",
        ]

        for class_name in class_options:
            try:
                search_box = wait_for_control(
                    root_web_area.EditControl,
                    {"ClassName": class_name},
                    search_depth=22,
                    timeout=2,
                )
            except TimeoutError:
                continue
            if search_box:
                break

        search_box.SetFocus()
        search_box_value_pattern = search_box.GetPattern(auto.PatternId.ValuePattern)
        search_box_value_pattern.SetValue(contractor_id)
        search_box.SendKeys("{ENTER}")

        time.sleep(sleep_time)

        table_dentists = wait_for_control(
            auto.TableControl,
            {"AutomationId": "dtRecipients"},
            search_depth=50,
        )
        grid_pattern = table_dentists.GetPattern(auto.PatternId.GridPattern)
        row_count = grid_pattern.RowCount

        is_phone_number_match = False

        if grid_pattern.GetItem(1, 0).Name == "Ingen data i tabellen":
            return {"rowCount": 0, "isPhoneNumberMatch": False}

        if row_count > 0:
            for row in range(row_count):
                phone_number = grid_pattern.GetItem(row, 5).Name
                if phone_number == clinic_phone_number:
                    is_phone_number_match = True
                    break
        return {"rowCount": row_count, "isPhoneNumberMatch": is_phone_number_match}
    except Exception as e:
        print(f"Error while checking contractor ID in EDI Portal: {e}")
        raise


def edi_portal_click_next_button(sleep_time: int) -> None:
    """
    Clicks the next button in the EDI portal.

    Args:
        sleep_time (int): Time to wait after clicking the next button.
    """
    print("[DEBUG] edi_portal_click_next_button: searching for Edge window...")
    try:
        edge_window = wait_for_control(
            auto.WindowControl, {"ClassName": "Chrome_WidgetWin_1"}, search_depth=3
        )

        edge_window.SetFocus()
        print(
            "[DEBUG] edi_portal_click_next_button: Edge window found, searching for Næste button..."
        )

        try:
            next_button = wait_for_control(
                edge_window.ButtonControl, {"Name": "Næste"}, search_depth=50, timeout=5
            )
        except TimeoutError:
            next_button = None

        if not next_button:
            print(
                "[DEBUG] edi_portal_click_next_button: Næste not found by name, trying AutomationId..."
            )
            try:
                next_button = wait_for_control(
                    edge_window.ButtonControl,
                    {"AutomationId": "patientInformationNextButton"},
                    search_depth=50,
                    timeout=5,
                )
            except TimeoutError:
                next_button = None

        if not next_button:
            raise RuntimeError("Next button not found in EDI Portal")
        print(
            f"[DEBUG] edi_portal_click_next_button: clicking button, then sleeping {sleep_time}s..."
        )
        next_button.Click(simulateMove=False, waitTime=0)
        time.sleep(sleep_time)
        print("[DEBUG] edi_portal_click_next_button: done.")
    except Exception as e:
        print(f"Error while clicking next button in EDI Portal: {e}")
        raise


def edi_portal_lookup_contractor_id(extern_clinic_data: dict) -> None:
    """
    Looks up the contractor ID in the EDI portal.

    Args:
        extern_clinic_data (dict): A dictionary containing the contractor ID and phone number.
    """
    try:
        if (
            extern_clinic_data[0]["contractorId"] == "477052"
            or extern_clinic_data[0]["contractorId"] == "470678"
        ):
            contractor_id = "485055"
        else:
            contractor_id = extern_clinic_data[0]["contractorId"]

        root_web_area = wait_for_control(
            auto.DocumentControl, {"AutomationId": "RootWebArea"}, search_depth=30
        )

        class_options = [
            "form-control filter_search",
            "form-control filter_search valid",
        ]

        for class_name in class_options:
            try:
                search_box = wait_for_control(
                    root_web_area.EditControl,
                    {"ClassName": class_name},
                    search_depth=22,
                    timeout=2,
                )
            except TimeoutError:
                continue
            if search_box:
                break

        search_box.SetFocus()
        search_box_value_pattern = search_box.GetPattern(auto.PatternId.ValuePattern)
        search_box_value_pattern.SetValue(contractor_id)
        search_box.SendKeys("{ENTER}")
        time.sleep(5)
    except Exception as e:
        print(f"Error while looking up contractor ID in EDI Portal: {e}")
        raise


def edi_portal_choose_receiver(extern_clinic_data: dict) -> None:
    """
    Chooses the receiver in the EDI portal based on a matching phone number.

    Args:
        extern_clinic_data (dict): A dictionary containing the contractor ID and phone number.
    """
    try:
        if (
            extern_clinic_data[0]["contractorId"] == "477052"
            or extern_clinic_data[0]["contractorId"] == "470678"
        ):
            clinic_phone_number = "86135240"
        else:
            clinic_phone_number = extern_clinic_data[0]["phoneNumber"]

        table_dentists = wait_for_control(
            auto.TableControl,
            {"AutomationId": "dtRecipients"},
            search_depth=50,
        )
        grid_pattern = table_dentists.GetPattern(auto.PatternId.GridPattern)
        row_count = grid_pattern.RowCount

        print(
            f"[DEBUG] clinic_phone_number='{clinic_phone_number}', row_count={row_count}"
        )

        if row_count > 0:
            for row in range(row_count):
                phone_number = grid_pattern.GetItem(row, 5).Name
                print(f"[DEBUG] row={row}, col5='{phone_number}'")
                if phone_number == clinic_phone_number:
                    grid_pattern.GetItem(row, 0).Click(simulateMove=False, waitTime=0)
                    print(f"[DEBUG] Clicked row {row}")
                    break
            else:
                print("[DEBUG] No matching phone number found — checkbox not clicked")
    except Exception as e:
        print(f"Error while choosing receiver in EDI Portal: {e}")
        raise


def edi_portal_add_content(
    queue_element: dict,
    edi_portal_content: dict,
    extern_clinic_data: dict,
    journal_continuation_text: str | None = None,
) -> None:
    """
    Adds content to the EDI portal based on the provided queue element and content template.

    Args:
        queue_element (dict): The queue element containing data for the content.
        edi_portal_content (dict): The content template for the EDI portal.
        journal_continuation_text (str | None): Additional text to be added to the content.
    """

    def _get_formatted_date(data) -> str:
        """
        Helper function to format the date from the data dictionary.
        Args:
            data (dict): The data dictionary containing the date information.
        Returns:
            str: The formatted date string or an error message.
        """
        try:
            locale.setlocale(locale.LC_TIME, "da_DK.UTF-8")
        except locale.Error:
            return "Error setting locale to Danish"

        if data.get("ukendt_dato") is True:
            return "Ukendt"

        try:
            date_str = data["dateOfExamination"]
            year, month, day = date_str.split("-")
            date_obj = date(int(year), int(month), int(day))
            return date_obj.strftime("%B %Y").capitalize()
        except (ValueError, KeyError):
            return "Error parsing date"

    subject = edi_portal_content["subject"]

    if not subject:
        raise ValueError("Subject is required.")

    if extern_clinic_data[0]["contractorId"] == "477052":
        subject = subject + " på Tandklinikken Hasle Torv"
    elif extern_clinic_data[0]["contractorId"] == "470678":
        subject = subject + " på Tandklinikken Brobjergparken"

    # Truncate subject to 66 characters to fit EDI portal limitations
    subject = subject[:66]

    body = edi_portal_content["body"]
    if not body:
        raise ValueError("Body is required.")

    examination_date = _get_formatted_date(data=queue_element)
    # risk_profile_map = {0: "Grøn", 1: "Gul", 2: "Rød", 3: "Ukendt"}
    # risc_profile = risk_profile_map.get(queue_element.get("riskProfil"))
    dental_plan = queue_element.get("tandplejeplan", "Ukendt")

    body_modified = re.sub(r"@examinationDate", examination_date, body)
    # body_modified = re.sub(r"@riscProfile", risc_profile, body_modified)
    if journal_continuation_text:
        if "Besked til privat tandlæge - Frit valg: " in journal_continuation_text:
            journal_continuation_text = journal_continuation_text.replace(
                "Besked til privat tandlæge - Frit valg: ", ""
            )
        elif (
            "Følgende oplysninger skal medsendes til privat tandlæge i forbindelse med udskrivning: "
            in journal_continuation_text
        ):
            journal_continuation_text = journal_continuation_text.replace(
                "Følgende oplysninger skal medsendes til privat tandlæge i forbindelse med udskrivning: ",
                "",
            )

    if dental_plan:
        body_modified = re.sub(
            r"@dentalPlan",
            f"Anden information: {journal_continuation_text}",
            body_modified,
        )
    else:
        body_modified = re.sub(r"@dentalPlan", "", body_modified)

    # Truncate body to 31150 characters to fit EDI portal limitations
    body_modified = body[:31150]

    try:
        root_web_area = wait_for_control(
            auto.DocumentControl, {"AutomationId": "RootWebArea"}, search_depth=30
        )

        subject_field = wait_for_control(
            root_web_area.EditControl,
            {"AutomationId": "ContentTitleInput"},
            search_depth=50,
        )
        subject_field_value_pattern = subject_field.GetPattern(
            auto.PatternId.ValuePattern
        )
        subject_field_value_pattern.SetValue(subject)

        body_field = wait_for_control(
            root_web_area.EditControl, {"AutomationId": "ContentInput"}, search_depth=50
        )
        body_field_value_pattern = body_field.GetPattern(auto.PatternId.ValuePattern)
        body_field_value_pattern.SetValue(body_modified)

    except Exception as e:
        print(f"Error while adding content in EDI Portal: {e}")
        raise


def edi_portal_upload_files(path_to_files: str) -> None:
    """
    Uploads files to the EDI portal.
    """
    upload_field = wait_for_control(
        auto.GroupControl, {"AutomationId": "createNewUpload"}, search_depth=50
    )
    upload_field.Click(simulateMove=False, waitTime=0)

    upload_dialog = wait_for_control(
        auto.WindowControl, {"Name": "Åbn"}, search_depth=5
    )

    upload_dialog_path_field = wait_for_control(
        upload_dialog.EditControl, {"ClassName": "Edit"}, search_depth=5
    )
    upload_dialog_value_pattern = upload_dialog_path_field.GetPattern(
        auto.PatternId.ValuePattern
    )
    upload_dialog_value_pattern.SetValue(path_to_files)
    upload_dialog.SendKeys("{ENTER}")

    root_web_area = wait_for_control(
        auto.DocumentControl, {"AutomationId": "RootWebArea"}, search_depth=30
    )

    element_gone = False
    timeout = 180  # Set a timeout for the upload progress check
    while not element_gone and timeout > 0:
        try:
            upload_progress = wait_for_control(
                root_web_area.TextControl,
                {
                    "Name": "En eller flere filer er under behandling. Du kan fortsætte til næste trin, når arbejdet er færdigt."
                },
                search_depth=20,
                timeout=5,
            )
            if upload_progress:
                time.sleep(5)
                timeout -= 5
                print(f"{timeout=}")
                print("Waiting for upload to finish...")
            else:
                element_gone = True
                print("Upload finished.")
        except TimeoutError:
            element_gone = True
            print("Upload progress element not found, assuming upload finished.")


def edi_portal_choose_priority(priority: str = "Rutine") -> None:
    """
    Chooses the priority in the EDI portal.

    Args:
        priority (str): The priority to be set.
    """
    try:
        priority_field = wait_for_control(
            auto.RadioButtonControl,
            {"Name": f"{priority}"},
            search_depth=21,
        )
        priority_field.Click(simulateMove=False, waitTime=0)
    except Exception as e:
        print(f"Error while choosing priority in EDI Portal: {e}")
        raise


def edi_portal_send_message() -> None:
    """
    Sends a message in the EDI portal.
    """
    try:
        root_web_area = wait_for_control(
            auto.DocumentControl, {"AutomationId": "RootWebArea"}, search_depth=30
        )

        send_message_button = wait_for_control(
            root_web_area.ButtonControl,
            {"AutomationId": "submitButton"},
            search_depth=4,
        )
        send_message_button.Click(simulateMove=False, waitTime=0)
        print("Message sent successfully.")
    except Exception as e:
        print(f"Error while sending message in EDI Portal: {e}")
        raise


def _find_latest_matching_row(grid_pattern, subject: str) -> int | None:
    """Find the most recent row in the sent grid matching the given subject."""

    def _parse_date(date_str: str) -> datetime | None:
        """Parse date from format like '11-09-2025 13:28'"""
        if not date_str:
            return None
        try:
            date, time = date_str.split(" ")
            day, month, year = date.split("-")
            hour, minute = time.split(":")
            return datetime(
                int(year), int(month), int(day), int(hour), int(minute), tzinfo=UTC
            )
        except ValueError:
            return None

    row_count = grid_pattern.RowCount
    latest_matching_row = None
    latest_date = None

    for row in range(1, row_count):
        message = grid_pattern.GetItem(row, 6).Name or ""
        date_str = grid_pattern.GetItem(row, 2).Name or ""

        if subject != message:
            continue

        parsed_date = _parse_date(date_str)
        if parsed_date is not None and (
            latest_date is None or parsed_date > latest_date
        ):
            latest_matching_row = row
            latest_date = parsed_date

    return latest_matching_row


def _get_receipt_download_menu(root_web_area) -> object:
    """Click into the dropdown menu for downloading a receipt, trying both CSS class variants."""
    menu_popup = None

    with suppress(TimeoutError):
        menu_popup = wait_for_control(
            root_web_area.ListControl,
            {"ClassName": "dropdown-menu show"},
            search_depth=50,
            timeout=15,
        )

    if not menu_popup:
        with suppress(TimeoutError):
            menu_popup = wait_for_control(
                root_web_area.ListControl,
                {"ClassName": "dropdown-menu"},
                search_depth=50,
                timeout=15,
            )

    if not menu_popup:
        raise TimeoutError("Could not find dropdown menu with any method")

    return wait_for_control(
        root_web_area.ListControl,
        {"ClassName": "dropdown-menu show"},
        search_depth=50,
    )


def _wait_for_receipt_download(timeout: int = 60) -> Path:
    """Poll the Downloads folder until a Meddelelse*.pdf appears."""
    download_path = Path.home() / "Downloads"
    start_time = time.time()

    while time.time() - start_time < timeout:
        receipt = next(download_path.glob("Meddelelse*.pdf"), None)
        if receipt is not None:
            print(f"Receipt downloaded: {receipt}")
            return receipt
        print("Waiting for receipt to download...")
        time.sleep(1)

    raise FileNotFoundError(
        "No file starting with 'Meddelelse' and ending with '.pdf' was found within the timeout period."
    )


def edi_portal_get_journal_sent_receip(subject: str) -> str:
    """
    Checks if the message was sent successfully in the EDI portal,
    and downloads the receipt.

    Args:
        subject (str): The subject of the message to check.

    Raises:
        RuntimeError: If the message was not sent successfully.
    """
    try:
        root_web_area = wait_for_control(
            auto.DocumentControl, {"AutomationId": "RootWebArea"}, search_depth=30
        )
        table_post_messages = wait_for_control(
            auto.TableControl, {"AutomationId": "dtSent"}, search_depth=50
        )
        grid_pattern = table_post_messages.GetPattern(auto.PatternId.GridPattern)

        latest_matching_row = _find_latest_matching_row(grid_pattern, subject)

        if latest_matching_row is None:
            print("Message not sent.")
            raise RuntimeError("Message not sent.")

        print(f"Using latest matching row {latest_matching_row}")

        # Get the row's Y coordinate from the grid cell (any column works for Y)
        row_cell = grid_pattern.GetItem(latest_matching_row, 0)
        table_rect = table_post_messages.BoundingRectangle
        row_rect = row_cell.BoundingRectangle
        row_y = (row_rect.top + row_rect.bottom) // 2

        # Step 1: hover over the row center to ensure the ... button is rendered
        row_center_x = (table_rect.left + table_rect.right) // 2
        print(
            f"[DEBUG] hovering row center at ({row_center_x}, {row_y}) to trigger ... button"
        )
        auto.MoveTo(row_center_x, row_y, moveSpeed=0.5, waitTime=0)
        time.sleep(0.5)

        # Step 2: find the ... button via proper tree traversal (not column index)
        def _find_first_button(ctrl, max_depth=10):
            if max_depth <= 0:
                return None
            for child in ctrl.GetChildren():
                if child.ControlType == auto.ControlType.ButtonControl:
                    return child
                found = _find_first_button(child, max_depth - 1)
                if found:
                    return found
            return None

        table_children = table_post_messages.GetChildren()
        print(f"[DEBUG] table has {len(table_children)} children")
        # children[0] = header row, data rows start at [1]
        target_row_ctrl = (
            table_children[latest_matching_row]
            if latest_matching_row < len(table_children)
            else None
        )
        print(f"[DEBUG] target_row_ctrl={target_row_ctrl}")

        dots_button = _find_first_button(target_row_ctrl) if target_row_ctrl else None
        print(f"[DEBUG] dots_button via tree={dots_button}")

        if dots_button:
            dots_pos = dots_button.GetClickablePoint()
            print(f"[DEBUG] moving to ... button at {dots_pos}")
            auto.MoveTo(dots_pos[0], dots_pos[1], moveSpeed=0.5, waitTime=0)
        else:
            # Fallback: midpoint between cell right and table right
            fallback_x = (row_rect.right + table_rect.right) // 2
            print(
                f"[DEBUG] button not found in tree, fallback hover at ({fallback_x}, {row_y})"
            )
            auto.MoveTo(fallback_x, row_y, moveSpeed=0.5, waitTime=0)
        time.sleep(1)

        # Find "Gem" item — control type unknown, search recursively by name
        def _find_gem_item(ctrl, depth=0, max_depth=15):
            if depth > max_depth:
                return None
            try:
                name = ctrl.Name or ""
                if (
                    name.strip() in ("Gem", "◄ Gem")
                    and ctrl.ControlType != auto.ControlType.DocumentControl
                ):
                    print(
                        f"[DEBUG] found Gem: type={ctrl.ControlType} name='{name}' class='{ctrl.ClassName}'"
                    )
                    return ctrl
            except Exception:
                pass
            for child in ctrl.GetChildren():
                result = _find_gem_item(child, depth + 1, max_depth)
                if result:
                    return result
            return None

        gem_item = _find_gem_item(root_web_area)
        if gem_item is None:
            raise RuntimeError("Could not find 'Gem' item in the dropdown")
        pos = gem_item.GetClickablePoint()
        print(f"[DEBUG] hovering Gem item at {pos}")
        auto.MoveTo(pos[0], pos[1], moveSpeed=0.5, waitTime=0)
        time.sleep(1)

        gem_som_pdf = wait_for_control(
            root_web_area.HyperlinkControl,
            {"Name": "Gem som PDF"},
            search_depth=50,
        )
        gem_som_pdf.Click(simulateMove=False, waitTime=0)

        return _wait_for_receipt_download()

    except Exception as e:
        print(f"Error while downloading the receipt from EDI Portal: {e}")
        raise


def rename_file(file_path: str, new_name: str, extension: str) -> str:
    """
    Renames a file and returns its new path.

    Args:
        file_path (str): Full path to the file to rename.
        new_name   (str): New filename without extension.
        extension  (str): New extension (e.g. '.pdf').

    Returns:
        str: Absolute path to the renamed file.

    Raises:
        FileNotFoundError: If the source file does not exist.
        OSError:           If the rename operation fails.
    """
    path = Path(file_path)

    if not path.exists():
        raise FileNotFoundError(f"File not found: {file_path}")

    new_file_path = path.parent / f"{new_name}{extension}"
    path.rename(new_file_path)
    return str(new_file_path)


def get_constants(conn_string: str, name: str) -> list:
    """Retrieve the constants from the database."""
    try:
        query = """
            SELECT
                *
            FROM
                [RPA].[rpa].[Constants]
            WHERE
                [name] = ?
        """
        params = (name,)

        with pyodbc.connect(conn_string) as conn, conn.cursor() as cursor:
            cursor.execute(query, params)
            columns = [column[0] for column in cursor.description]
            constant_value = [
                dict(zip(columns, row, strict=True)) for row in cursor.fetchall()
            ]
        return constant_value
    except pyodbc.Error as e:
        print(f"Database error: {e}")
        raise
    except Exception as e:
        print(f"Error retrieving constants: {e}")
        raise


def edi_portal_is_patient_data_sent(subject: str) -> bool:
    """
    Checks if the patient data has been sent in the EDI portal.

    Returns:
        bool: True if the patient data has been sent, False otherwise.
    """

    def _parse_date(date_str: str) -> datetime | None:
        """Parse date from format like '11-09-2025 13:28'"""
        if not date_str:
            return None
        try:
            date, time = date_str.split(" ")
            day, month, year = date.split("-")
            hour, minute = time.split(":")
            return datetime(
                int(year), int(month), int(day), int(hour), int(minute), tzinfo=UTC
            )
        except ValueError:
            return None

    print(
        f"[DEBUG] edi_portal_is_patient_data_sent: checking if already sent for subject='{subject}'"
    )
    try:
        url_field = wait_for_control(
            auto.EditControl, {"Name": "Address and search bar"}, search_depth=25
        )
        url_field_value_pattern = url_field.GetPattern(auto.PatternId.ValuePattern)
        url_field_value_pattern.SetValue("https://ediportalen.dk/Messages/Sent")
        url_field.SendKeys("{ENTER}")
        print(
            "[DEBUG] edi_portal_is_patient_data_sent: navigating to Sent page, sleeping 5s..."
        )
        time.sleep(5)

        test = wait_for_control(
            auto.WindowControl, {"ClassName": "Chrome_WidgetWin_1"}, search_depth=3
        )

        test.SetFocus()
        next_test = wait_for_control(
            test.PaneControl, {"ClassName": "BrowserRootView"}, search_depth=4
        )

        table_post_messages = wait_for_control(
            next_test.TableControl, {"AutomationId": "dtSent"}, search_depth=50
        )
        grid_pattern = table_post_messages.GetPattern(auto.PatternId.GridPattern)
        row_count = grid_pattern.RowCount
        success_message = False

        # if row_count > 0:
        #     for row in range(1, row_count):
        #         message = grid_pattern.GetItem(row, 5).Name
        #         print(f"{subject=}, {message=}")
        #         if subject == message:
        #             success_message = True
        #             break

        # Define one month ago here
        one_month_ago = datetime.now(UTC) - timedelta(days=30)

        if row_count > 0:
            for row in range(1, row_count):
                message = grid_pattern.GetItem(row, 6).Name or ""
                date_str = grid_pattern.GetItem(row, 2).Name or ""

                print(f"Row {row}: message='{message}', date='{date_str}'")

                # Check if message contains the target text
                if subject not in message:
                    continue

                # Parse and check if date is older than 1 month
                parsed_date = _parse_date(date_str)
                if parsed_date is None:
                    print(f"Could not parse date: {date_str}")
                    continue

                # Both conditions must be true: message contains subject AND date is older than 1 month
                if parsed_date > one_month_ago:
                    success_message = True
                    print(
                        f"Found matching row {row}: message contains '{subject}' and date {parsed_date} is older than 1 month"
                    )
                    break

                print(
                    f"Message contains '{subject}' but date {parsed_date} is not older than 1 month"
                )

        print(
            f"[DEBUG] edi_portal_is_patient_data_sent: success_message={success_message}"
        )
        if success_message:
            print(
                "[DEBUG] edi_portal_is_patient_data_sent: already sent → returning True"
            )
            return True

        print("[DEBUG] edi_portal_is_patient_data_sent: not sent → returning False")
        return False
    except TimeoutError:
        print("[DEBUG] edi_portal_is_patient_data_sent: TimeoutError → returning False")
        return False
    except Exception as e:
        print(f"Error while checking if patient data is sent in EDI Portal: {e}")
        raise


def edi_portal_go_to_send_journal() -> None:
    """
    Navigates to the 'Opret ny journalforsendelse' section in the EDI portal.
    """
    try:
        url_field = wait_for_control(
            auto.EditControl, {"Name": "Address and search bar"}, search_depth=25
        )
        url_field_value_pattern = url_field.GetPattern(auto.PatternId.ValuePattern)
        url_field_value_pattern.SetValue("https://ediportalen.dk/Journal/Create")
        url_field.SendKeys("{ENTER}")
        print("[DEBUG] edi_portal_go_to_send_journal: navigating, sleeping 5s...")
        time.sleep(5)
        print("[DEBUG] edi_portal_go_to_send_journal: done.")
    except Exception as e:
        print(f"Error while navigating to 'Send journal' in EDI Portal: {e}")
        raise
