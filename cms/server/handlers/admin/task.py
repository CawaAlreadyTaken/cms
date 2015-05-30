#!/usr/bin/env python2
# -*- coding: utf-8 -*-

# Contest Management System - http://cms-dev.github.io/
# Copyright © 2010-2013 Giovanni Mascellani <mascellani@poisson.phc.unipi.it>
# Copyright © 2010-2015 Stefano Maggiolo <s.maggiolo@gmail.com>
# Copyright © 2010-2012 Matteo Boscariol <boscarim@hotmail.com>
# Copyright © 2012-2014 Luca Wehrstedt <luca.wehrstedt@gmail.com>
# Copyright © 2014 Artem Iglikov <artem.iglikov@gmail.com>
# Copyright © 2014 Fabian Gundlach <320pointsguy@gmail.com>
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

"""Task-related handlers for AWS.

"""

from __future__ import absolute_import
from __future__ import print_function
from __future__ import unicode_literals

import logging
import traceback

import tornado.web

from cms.db import Attachment, Dataset, Session, Statement, Submission, Task
from cmscommon.datetime import make_datetime

from .base import BaseHandler


logger = logging.getLogger(__name__)


class AddTaskHandler(BaseHandler):
    def get(self):
        self.r_params = self.render_params()
        self.render("add_task.html", **self.r_params)

    def post(self):
        fallback_page = "/tasks/new"

        try:
            attrs = dict()

            self.get_string(attrs, "name", empty=None)
            self.get_string(attrs, "title")

            assert attrs.get("name") is not None, "No task name specified."

            self.get_string(attrs, "primary_statements")

            self.get_submission_format(attrs)

            self.get_string(attrs, "token_mode")
            self.get_int(attrs, "token_max_number")
            self.get_timedelta_sec(attrs, "token_min_interval")
            self.get_int(attrs, "token_gen_initial")
            self.get_int(attrs, "token_gen_number")
            self.get_timedelta_min(attrs, "token_gen_interval")
            self.get_int(attrs, "token_gen_max")

            self.get_int(attrs, "max_submission_number")
            self.get_int(attrs, "max_user_test_number")
            self.get_timedelta_sec(attrs, "min_submission_interval")
            self.get_timedelta_sec(attrs, "min_user_test_interval")

            self.get_int(attrs, "score_precision")

            self.get_string(attrs, "score_mode")

            # Create the task.
            task = Task(**attrs)
            self.sql_session.add(task)

        except Exception as error:
            self.application.service.add_notification(
                make_datetime(), "Invalid field(s)", repr(error))
            self.redirect(fallback_page)
            return

        try:
            attrs = dict()

            self.get_time_limit(attrs, "time_limit")
            self.get_memory_limit(attrs, "memory_limit")
            self.get_task_type(attrs, "task_type", "TaskTypeOptions_")
            self.get_score_type(attrs, "score_type", "score_type_parameters")

            # Create its first dataset.
            attrs["description"] = "Default"
            attrs["autojudge"] = True
            attrs["task"] = task
            dataset = Dataset(**attrs)
            self.sql_session.add(dataset)

            # Make the dataset active. Life works better that way.
            task.active_dataset = dataset

        except Exception as error:
            self.application.service.add_notification(
                make_datetime(), "Invalid field(s)", repr(error))
            self.redirect(fallback_page)
            return

        if self.try_commit():
            # Create the task on RWS.
            self.application.service.proxy_service.reinitialize()
            self.redirect("/task/%s" % task.id)
        else:
            self.redirect(fallback_page)


class TaskHandler(BaseHandler):
    """Task handler, with a POST method to edit the task.

    """
    def get(self, task_id):
        task = self.safe_get_item(Task, task_id)

        self.r_params = self.render_params()
        self.r_params["task"] = task
        self.r_params["submissions"] = \
            self.sql_session.query(Submission)\
                .join(Task).filter(Task.id == task_id)\
                .order_by(Submission.timestamp.desc()).all()
        self.render("task.html", **self.r_params)

    def post(self, task_id):
        task = self.safe_get_item(Task, task_id)

        try:
            attrs = task.get_attrs()

            self.get_string(attrs, "name", empty=None)
            self.get_string(attrs, "title")

            assert attrs.get("name") is not None, "No task name specified."

            self.get_string(attrs, "primary_statements")

            self.get_submission_format(attrs)

            self.get_string(attrs, "token_mode")
            self.get_int(attrs, "token_max_number")
            self.get_timedelta_sec(attrs, "token_min_interval")
            self.get_int(attrs, "token_gen_initial")
            self.get_int(attrs, "token_gen_number")
            self.get_timedelta_min(attrs, "token_gen_interval")
            self.get_int(attrs, "token_gen_max")

            self.get_int(attrs, "max_submission_number")
            self.get_int(attrs, "max_user_test_number")
            self.get_timedelta_sec(attrs, "min_submission_interval")
            self.get_timedelta_sec(attrs, "min_user_test_interval")

            self.get_int(attrs, "score_precision")

            self.get_string(attrs, "score_mode")

            # Update the task.
            task.set_attrs(attrs)

        except Exception as error:
            self.application.service.add_notification(
                make_datetime(), "Invalid field(s)", repr(error))
            self.redirect("/task/%s" % task_id)
            return

        for dataset in task.datasets:
            try:
                attrs = dataset.get_attrs()

                self.get_time_limit(attrs, "time_limit_%d" % dataset.id)
                self.get_memory_limit(attrs, "memory_limit_%d" % dataset.id)
                self.get_task_type(attrs, "task_type_%d" % dataset.id,
                                   "TaskTypeOptions_%d_" % dataset.id)
                self.get_score_type(attrs, "score_type_%d" % dataset.id,
                                    "score_type_parameters_%d" % dataset.id)

                # Update the dataset.
                dataset.set_attrs(attrs)

            except Exception as error:
                self.application.service.add_notification(
                    make_datetime(), "Invalid field(s)", repr(error))
                self.redirect("/task/%s" % task_id)
                return

            for testcase in dataset.testcases.itervalues():
                testcase.public = bool(self.get_argument(
                    "testcase_%s_public" % testcase.id, False))

        if self.try_commit():
            # Update the task and score on RWS.
            self.application.service.proxy_service.dataset_updated(
                task_id=task.id)
        self.redirect("/task/%s" % task_id)


class AddStatementHandler(BaseHandler):
    """Add a statement to a task.

    """
    def get(self, task_id):
        task = self.safe_get_item(Task, task_id)

        self.r_params = self.render_params()
        self.r_params["task"] = task
        self.render("add_statement.html", **self.r_params)

    def post(self, task_id):
        fallback_page = "/task/%s/statements/add" % task_id

        task = self.safe_get_item(Task, task_id)

        language = self.get_argument("language", None)
        if language is None:
            self.application.service.add_notification(
                make_datetime(),
                "No language code specified",
                "The language code can be any string.")
            self.redirect(fallback_page)
            return
        statement = self.request.files["statement"][0]
        if not statement["filename"].endswith(".pdf"):
            self.application.service.add_notification(
                make_datetime(),
                "Invalid task statement",
                "The task statement must be a .pdf file.")
            self.redirect(fallback_page)
            return
        task_name = task.name
        self.sql_session.close()

        try:
            digest = self.application.service.file_cacher.put_file_content(
                statement["body"],
                "Statement for task %s (lang: %s)" % (task_name, language))
        except Exception as error:
            self.application.service.add_notification(
                make_datetime(),
                "Task statement storage failed",
                repr(error))
            self.redirect(fallback_page)
            return

        # TODO verify that there's no other Statement with that language
        # otherwise we'd trigger an IntegrityError for constraint violation

        self.sql_session = Session()
        task = self.safe_get_item(Task, task_id)
        self.contest = task.contest

        statement = Statement(language, digest, task=task)
        self.sql_session.add(statement)

        if self.try_commit():
            self.redirect("/task/%s" % task_id)
        else:
            self.redirect(fallback_page)


class DeleteStatementHandler(BaseHandler):
    """Delete a statement.

    """
    def get(self, task_id, statement_id):
        statement = self.safe_get_item(Statement, statement_id)
        task = self.safe_get_item(Task, task_id)

        # Protect against URLs providing incompatible parameters.
        if task is not statement.task:
            raise tornado.web.HTTPError(404)

        self.sql_session.delete(statement)

        self.try_commit()
        self.redirect("/task/%s" % task.id)


class AddAttachmentHandler(BaseHandler):
    """Add an attachment to a task.

    """
    def get(self, task_id):
        task = self.safe_get_item(Task, task_id)

        self.r_params = self.render_params()
        self.r_params["task"] = task
        self.render("add_attachment.html", **self.r_params)

    def post(self, task_id):
        fallback_page = "/task/%s/attachments/add" % task_id

        task = self.safe_get_item(Task, task_id)

        attachment = self.request.files["attachment"][0]
        task_name = task.name
        self.sql_session.close()

        try:
            digest = self.application.service.file_cacher.put_file_content(
                attachment["body"],
                "Task attachment for %s" % task_name)
        except Exception as error:
            self.application.service.add_notification(
                make_datetime(),
                "Attachment storage failed",
                repr(error))
            self.redirect(fallback_page)
            return

        # TODO verify that there's no other Attachment with that filename
        # otherwise we'd trigger an IntegrityError for constraint violation

        self.sql_session = Session()
        task = self.safe_get_item(Task, task_id)

        attachment = Attachment(attachment["filename"], digest, task=task)
        self.sql_session.add(attachment)

        if self.try_commit():
            self.redirect("/task/%s" % task_id)
        else:
            self.redirect(fallback_page)


class DeleteAttachmentHandler(BaseHandler):
    """Delete an attachment.

    """
    def get(self, task_id, attachment_id):
        attachment = self.safe_get_item(Attachment, attachment_id)
        task = self.safe_get_item(Task, task_id)

        # Protect against URLs providing incompatible parameters.
        if attachment.task is not task:
            raise tornado.web.HTTPError(404)

        self.sql_session.delete(attachment)

        self.try_commit()
        self.redirect("/task/%s" % task.id)


class AddDatasetHandler(BaseHandler):
    """Add a new, clean dataset to a task.

    It's equivalent to the old behavior when the dataset_id_to_copy
    given was equal to the string "-".

    If referred by GET, this handler will return a HTML form.
    If referred by POST, this handler will create the dataset.
    """
    def get(self, task_id):
        task = self.safe_get_item(Task, task_id)

        original_dataset = None
        description = "Default"

        self.r_params = self.render_params()
        self.r_params["task"] = task
        self.r_params["clone_id"] = "new"
        self.r_params["original_dataset"] = original_dataset
        self.r_params["original_dataset_task_type_parameters"] = None
        self.r_params["default_description"] = description
        self.render("add_dataset.html", **self.r_params)

    def post(self, task_id):
        fallback_page = "/task/%s/new_dataset" % task_id

        task = self.safe_get_item(Task, task_id)

        try:
            attrs = dict()

            self.get_string(attrs, "description")

            # Ensure description is unique.
            if any(attrs["description"] == d.description
                   for d in task.datasets):
                self.application.service.add_notification(
                    make_datetime(),
                    "Dataset name %r is already taken." % attrs["description"],
                    "Please choose a unique name for this dataset.")
                self.redirect(fallback_page)
                return

            self.get_time_limit(attrs, "time_limit")
            self.get_memory_limit(attrs, "memory_limit")
            self.get_task_type(attrs, "task_type", "TaskTypeOptions_")
            self.get_score_type(attrs, "score_type", "score_type_parameters")

            # Create the dataset.
            attrs["autojudge"] = False
            attrs["task"] = task
            dataset = Dataset(**attrs)
            self.sql_session.add(dataset)

        except Exception as error:
            logger.warning("Invalid field: %s" % (traceback.format_exc()))
            self.application.service.add_notification(
                make_datetime(), "Invalid field(s)", repr(error))
            self.redirect(fallback_page)
            return

        # If the task does not yet have an active dataset, make this
        # one active.
        if task.active_dataset is None:
            task.active_dataset = dataset

        if self.try_commit():
            # self.application.service.scoring_service.reinitialize()
            self.redirect("/task/%s" % task_id)
        else:
            self.redirect(fallback_page)
